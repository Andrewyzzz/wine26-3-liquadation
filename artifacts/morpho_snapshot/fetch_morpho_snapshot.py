#!/usr/bin/env python3
"""Fetch a Morpho active-market graph and find an odd collateral-loan cycle.

The graph has one undirected edge per active Morpho market:
collateralAsset -- loanAsset.  A market is active at threshold T if both
borrowAssetsUsd and collateralAssetsUsd are at least T.  This is a realized
aggregate exposure witness, not a worst-case hardness claim.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import json
import pathlib
import ssl
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections import defaultdict, deque


API = "https://api.morpho.org/graphql"


MARKETS_QUERY = """
query Markets($first: Int!, $skip: Int!, $chainIds: [Int!]) {
  markets(
    first: $first
    skip: $skip
    orderBy: BorrowAssetsUsd
    orderDirection: Desc
    where: { chainId_in: $chainIds }
  ) {
    items {
      marketId
      chain { id network }
      loanAsset { address symbol decimals }
      collateralAsset { address symbol decimals }
      oracle { address }
      lltv
      state {
        borrowAssets
        borrowAssetsUsd
        collateralAssets
        collateralAssetsUsd
        supplyAssetsUsd
        liquidityAssetsUsd
      }
    }
  }
}
"""


def graphql(query: str, variables: dict, insecure_tls: bool = False, use_curl: bool = False, retries: int = 4) -> dict:
    payload = json.dumps({"query": query, "variables": variables}).encode()
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            if use_curl:
                cmd = [
                    "curl",
                    "-sS",
                    "-X",
                    "POST",
                    API,
                    "-H",
                    "content-type: application/json",
                    "--data-binary",
                    payload.decode(),
                ]
                if insecure_tls:
                    cmd.insert(1, "-k")
                proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
                out = json.loads(proc.stdout)
                if out.get("errors"):
                    raise RuntimeError(json.dumps(out["errors"], indent=2))
                return out["data"]

            req = urllib.request.Request(
                API,
                data=payload,
                headers={"content-type": "application/json", "accept": "application/json"},
                method="POST",
            )
            context = ssl._create_unverified_context() if insecure_tls else None
            with urllib.request.urlopen(req, timeout=60, context=context) as resp:
                out = json.loads(resp.read().decode())
            if out.get("errors"):
                raise RuntimeError(json.dumps(out["errors"], indent=2))
            return out["data"]
        except Exception as exc:  # noqa: BLE001 - command-line artifact wants retry.
            last_exc = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise

    assert last_exc is not None
    raise last_exc


def fetch_markets(
    chain_ids: list[int],
    page_size: int,
    insecure_tls: bool,
    use_curl: bool,
    max_pages: int | None,
) -> list[dict]:
    markets: list[dict] = []
    skip = 0
    pages = 0
    while True:
        if max_pages is not None and pages >= max_pages:
            return markets
        data = graphql(
            MARKETS_QUERY,
            {"first": page_size, "skip": skip, "chainIds": chain_ids},
            insecure_tls=insecure_tls,
            use_curl=use_curl,
        )
        items = data["markets"]["items"]
        markets.extend(items)
        pages += 1
        if len(items) < page_size:
            return markets
        skip += page_size


def usd(value) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def symbol(asset: dict) -> str:
    sym = asset.get("symbol") or asset.get("address") or "UNKNOWN"
    return sym.replace("$", "\\$")


def active_edges(markets: list[dict], threshold: float) -> list[dict]:
    edges = []
    for m in markets:
        st = m.get("state") or {}
        borrow = usd(st.get("borrowAssetsUsd"))
        collat = usd(st.get("collateralAssetsUsd"))
        if borrow < threshold or collat < threshold:
            continue
        loan = m.get("loanAsset") or {}
        coll = m.get("collateralAsset") or {}
        if not loan.get("address") or not coll.get("address"):
            continue
        if loan["address"].lower() == coll["address"].lower():
            continue
        edges.append(
            {
                "marketId": m["marketId"],
                "chainId": (m.get("chain") or {}).get("id"),
                "collateral_symbol": symbol(coll),
                "collateral_address": coll["address"],
                "loan_symbol": symbol(loan),
                "loan_address": loan["address"],
                "borrow_usd": borrow,
                "collateral_usd": collat,
            }
        )
    return edges


def canonical_node(sym: str, addr: str) -> str:
    return f"{sym} ({addr[:6]}...{addr[-4:]})"


def build_graph(edges: list[dict]):
    adj: dict[str, set[str]] = defaultdict(set)
    edge_by_pair: dict[tuple[str, str], dict] = {}
    for e in edges:
        u = canonical_node(e["collateral_symbol"], e["collateral_address"])
        v = canonical_node(e["loan_symbol"], e["loan_address"])
        adj[u].add(v)
        adj[v].add(u)
        key = tuple(sorted((u, v)))
        old = edge_by_pair.get(key)
        if old is None or e["borrow_usd"] > old["borrow_usd"]:
            edge_by_pair[key] = e
    return adj, edge_by_pair


def odd_cycle(adj: dict[str, set[str]]) -> list[str] | None:
    color: dict[str, int] = {}
    parent: dict[str, str | None] = {}
    for start in sorted(adj):
        if start in color:
            continue
        color[start] = 0
        parent[start] = None
        q = deque([start])
        while q:
            u = q.popleft()
            for v in sorted(adj[u]):
                if v not in color:
                    color[v] = 1 - color[u]
                    parent[v] = u
                    q.append(v)
                elif color[v] == color[u]:
                    return reconstruct_cycle(u, v, parent)
    return None


def reconstruct_cycle(u: str, v: str, parent: dict[str, str | None]) -> list[str]:
    def path_to_root(x: str) -> list[str]:
        path = []
        while x is not None:
            path.append(x)
            x = parent[x]
        return path

    pu = path_to_root(u)
    pv = path_to_root(v)
    pos_u = {node: i for i, node in enumerate(pu)}
    lca = next(node for node in pv if node in pos_u)
    left = pu[: pos_u[lca] + 1]
    right = pv[: pv.index(lca)]
    return left + right[::-1] + [u]


def write_csv(path: pathlib.Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def summarize(markets: list[dict], thresholds: list[float], out_dir: pathlib.Path) -> dict:
    summaries = []
    primary_edges = []
    primary_cycle = None
    primary_threshold = None
    for t in thresholds:
        edges = active_edges(markets, t)
        adj, edge_by_pair = build_graph(edges)
        cyc = odd_cycle(adj)
        summaries.append(
            {
                "threshold_usd": t,
                "active_edges": len(edge_by_pair),
                "assets": len(adj),
                "bipartite": cyc is None,
                "odd_cycle": cyc or [],
            }
        )
        if cyc:
            primary_edges = edges
            primary_cycle = cyc
            primary_threshold = t

    if primary_cycle is None:
        primary_edges = active_edges(markets, thresholds[0])

    write_csv(out_dir / "active_edges.csv", primary_edges)
    (out_dir / "odd_cycle.json").write_text(
        json.dumps({"cycle": primary_cycle or [], "thresholds": summaries}, indent=2),
        encoding="utf-8",
    )

    return {"summaries": summaries, "primary_cycle": primary_cycle or [], "primary_threshold_usd": primary_threshold}


def latex_summary(result: dict, generated_at: str) -> str:
    rows = []
    for s in result["summaries"]:
        cyc = "--" if not s["odd_cycle"] else "yes"
        rows.append(
            f"{s['threshold_usd']:,.0f} & {s['assets']} & {s['active_edges']} & "
            f"{'yes' if s['bipartite'] else 'no'} & {cyc} \\\\"
        )
    cycle = result["primary_cycle"]
    threshold = result.get("primary_threshold_usd")
    cycle_text = " -- ".join(cycle) if cycle else "No odd cycle found at the tested thresholds."
    return f"""% Auto-generated by artifacts/morpho_snapshot/fetch_morpho_snapshot.py
% Generated at {generated_at}.
\\begin{{tabular}}{{rrrrl}}
\\toprule
Threshold (USD) & Assets & Active edges & Bipartite? & Odd cycle \\\\
\\midrule
{chr(10).join(rows)}
\\bottomrule
\\end{{tabular}}

Odd-cycle witness at threshold USD {threshold:,.0f}: {cycle_text}.
"""


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--chain-id", type=int, default=1)
    parser.add_argument("--page-size", type=int, default=1000)
    parser.add_argument("--max-pages", type=int, default=None, help="Optional page cap for reproducible bounded snapshots.")
    parser.add_argument("--thresholds", default="0,100,1000,10000")
    parser.add_argument("--out", default="artifacts/morpho_snapshot")
    parser.add_argument("--raw-input", default=None, help="Reuse a saved raw_markets.json instead of fetching.")
    parser.add_argument("--insecure-tls", action="store_true", help="Disable TLS certificate verification for local snapshot fetching.")
    parser.add_argument("--use-curl", action="store_true", help="Use curl for GraphQL requests instead of urllib.")
    args = parser.parse_args()

    out_dir = pathlib.Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    generated_at = dt.datetime.now(dt.timezone.utc).isoformat()

    if args.raw_input:
        markets = json.loads(pathlib.Path(args.raw_input).read_text(encoding="utf-8"))
    else:
        markets = fetch_markets([args.chain_id], args.page_size, args.insecure_tls, args.use_curl, args.max_pages)
    (out_dir / "raw_markets.json").write_text(json.dumps(markets, indent=2), encoding="utf-8")
    thresholds = [float(x) for x in args.thresholds.split(",") if x.strip()]
    result = summarize(markets, thresholds, out_dir)
    meta = {
        "generated_at_utc": generated_at,
        "api": API,
        "chain_id": args.chain_id,
        "markets_total": len(markets),
        "page_size": args.page_size,
        "max_pages": args.max_pages,
        "thresholds_usd": thresholds,
        "insecure_tls": args.insecure_tls,
        "use_curl": args.use_curl,
        "primary_cycle": result["primary_cycle"],
        "primary_threshold_usd": result["primary_threshold_usd"],
        "note": "Morpho API snapshot; raw response is saved for reproducibility.",
    }
    (out_dir / "summary.json").write_text(json.dumps({**meta, **result}, indent=2), encoding="utf-8")
    (out_dir / "summary.tex").write_text(latex_summary(result, generated_at), encoding="utf-8")
    print(json.dumps(meta, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
