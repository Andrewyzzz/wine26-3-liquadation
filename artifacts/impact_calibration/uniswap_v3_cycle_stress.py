#!/usr/bin/env python3
"""Uniswap v3 depth stress calibration for a Morpho odd-cycle witness.

This script is intentionally a stress calibration rather than a protocol oracle
claim. It combines:

* aggregate active Morpho market exposures from artifacts/morpho_snapshot, and
* live Uniswap v3 active-liquidity state at a fixed Ethereum block.

For each directed Morpho edge in a hand-picked mainstream odd cycle, it finds
the deepest Uniswap v3 pool among standard fee tiers and reports how large a
small fraction of the Morpho collateral exposure is relative to the active
virtual reserve of the collateral token.
"""

from __future__ import annotations

import csv
import json
import pathlib
import subprocess
import time
from dataclasses import dataclass
from decimal import Decimal, getcontext


getcontext().prec = 80

RPC_URL = "https://ethereum.publicnode.com"
UNISWAP_V3_FACTORY = "0x1F98431c8aD98523631AE4a59f267346ea31F984"
Q96 = Decimal(2) ** 96
FEES = [100, 500, 3000, 10000]

TOKENS = {
    "USDC": {
        "address": "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",
        "decimals": 6,
    },
    "WETH": {
        "address": "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",
        "decimals": 18,
    },
    "WBTC": {
        "address": "0x2260FAC5E5542a773Aa44fBCfeDf7C193bc2C599",
        "decimals": 8,
    },
}

# Directed Morpho edges used by the realized odd cycle
# USDC -- WBTC -- WETH -- USDC.
CYCLE_EDGES = [
    ("WBTC", "USDC"),
    ("WBTC", "WETH"),
    ("WETH", "USDC"),
]

SALE_FRACTIONS = [Decimal("0.01"), Decimal("0.05"), Decimal("0.10")]
ETA_VALUES = [Decimal("0.005"), Decimal("0.01"), Decimal("0.02"), Decimal("0.05")]


def run_curl(payload: object, retries: int = 6) -> object:
    cmd = [
        "curl",
        "-sS",
        "-X",
        "POST",
        RPC_URL,
        "-H",
        "content-type: application/json",
        "--data-binary",
        json.dumps(payload),
    ]
    last: Exception | None = None
    for attempt in range(retries):
        try:
            proc = subprocess.run(cmd, check=True, capture_output=True, text=True)
            out = json.loads(proc.stdout)
            if isinstance(out, list):
                for item in out:
                    if "error" in item:
                        raise RuntimeError(json.dumps(item["error"], indent=2))
            elif "error" in out:
                raise RuntimeError(json.dumps(out["error"], indent=2))
            return out
        except Exception as exc:  # noqa: BLE001 - command-line reproducibility artifact.
            last = exc
            if attempt + 1 < retries:
                time.sleep(1.5 * (attempt + 1))
                continue
            raise
    assert last is not None
    raise last


def rpc(method: str, params: list) -> object:
    out = run_curl({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
    return out["result"]


def eth_call(to: str, data: str, block: str) -> str:
    return rpc("eth_call", [{"to": to, "data": data}, block])


def pad_address(addr: str) -> str:
    return addr.lower().removeprefix("0x").rjust(64, "0")


def pad_uint(value: int) -> str:
    return hex(value)[2:].rjust(64, "0")


def get_pool(token_a: str, token_b: str, fee: int, block: str) -> str | None:
    a = token_a.lower()
    b = token_b.lower()
    if int(a, 16) > int(b, 16):
        a, b = b, a
    # getPool(address,address,uint24)
    data = "0x1698ee82" + pad_address(a) + pad_address(b) + pad_uint(fee)
    raw = eth_call(UNISWAP_V3_FACTORY, data, block)
    addr = "0x" + raw[-40:]
    if int(addr, 16) == 0:
        return None
    return addr


def parse_uint(raw: str) -> int:
    return int(raw, 16)


def parse_address(raw: str) -> str:
    return "0x" + raw[-40:]


def parse_slot0(raw: str) -> dict:
    body = raw.removeprefix("0x")
    words = [body[i : i + 64] for i in range(0, len(body), 64)]
    return {
        "sqrtPriceX96": int(words[0], 16),
        "tick": int(words[1], 16) if int(words[1], 16) < 2**255 else int(words[1], 16) - 2**256,
    }


def call_pool(pool: str, block: str) -> dict:
    # token0(), token1(), liquidity(), slot0()
    batch = [
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "eth_call",
            "params": [{"to": pool, "data": "0x0dfe1681"}, block],
        },
        {
            "jsonrpc": "2.0",
            "id": 2,
            "method": "eth_call",
            "params": [{"to": pool, "data": "0xd21220a7"}, block],
        },
        {
            "jsonrpc": "2.0",
            "id": 3,
            "method": "eth_call",
            "params": [{"to": pool, "data": "0x1a686502"}, block],
        },
        {
            "jsonrpc": "2.0",
            "id": 4,
            "method": "eth_call",
            "params": [{"to": pool, "data": "0x3850c7bd"}, block],
        },
    ]
    out = {item["id"]: item["result"] for item in run_curl(batch)}
    token0 = parse_address(out[1])
    token1 = parse_address(out[2])
    liquidity = parse_uint(out[3])
    slot0 = parse_slot0(out[4])
    return {
        "pool": pool,
        "token0": token0,
        "token1": token1,
        "liquidity": liquidity,
        **slot0,
    }


def token_by_address() -> dict[str, str]:
    return {v["address"].lower(): k for k, v in TOKENS.items()}


def decimal_amount(raw_amount: Decimal, decimals: int) -> Decimal:
    return raw_amount / (Decimal(10) ** decimals)


def virtual_reserves(pool_state: dict) -> dict[str, Decimal]:
    by_addr = token_by_address()
    token0 = by_addr[pool_state["token0"].lower()]
    token1 = by_addr[pool_state["token1"].lower()]
    sqrtp = Decimal(pool_state["sqrtPriceX96"]) / Q96
    liquidity = Decimal(pool_state["liquidity"])
    reserve0_raw = liquidity / sqrtp
    reserve1_raw = liquidity * sqrtp
    return {
        token0: decimal_amount(reserve0_raw, TOKENS[token0]["decimals"]),
        token1: decimal_amount(reserve1_raw, TOKENS[token1]["decimals"]),
    }


def implied_prices_usd(pool_state: dict) -> dict[str, Decimal]:
    by_addr = token_by_address()
    token0 = by_addr[pool_state["token0"].lower()]
    token1 = by_addr[pool_state["token1"].lower()]
    sqrtp = Decimal(pool_state["sqrtPriceX96"]) / Q96
    price1_per_0 = (sqrtp * sqrtp) * (Decimal(10) ** (TOKENS[token0]["decimals"] - TOKENS[token1]["decimals"]))
    if token1 == "USDC":
        return {token1: Decimal(1), token0: price1_per_0}
    if token0 == "USDC":
        return {token0: Decimal(1), token1: Decimal(1) / price1_per_0}
    return {}


def find_best_pools(block: str) -> dict[tuple[str, str], dict]:
    states: dict[tuple[str, str], list[dict]] = {}
    for a, b in {tuple(sorted(edge)) for edge in CYCLE_EDGES}:
        states[(a, b)] = []
        for fee in FEES:
            pool = get_pool(TOKENS[a]["address"], TOKENS[b]["address"], fee, block)
            if not pool:
                continue
            st = call_pool(pool, block)
            st["fee"] = fee
            st["pair"] = (a, b)
            st["reserves"] = virtual_reserves(st)
            states[(a, b)].append(st)

    # First determine USD prices from deepest USDC pools.
    prices = {"USDC": Decimal(1)}
    for pair in [tuple(sorted(("WBTC", "USDC"))), tuple(sorted(("WETH", "USDC")))]:
        candidates = states[pair]
        priced = []
        for st in candidates:
            local = implied_prices_usd(st)
            if local:
                token = "WBTC" if "WBTC" in pair else "WETH"
                reserve_usd = st["reserves"][token] * local[token]
                priced.append((reserve_usd, st, local[token]))
        priced.sort(key=lambda x: x[0], reverse=True)
        if priced:
            _, st, price = priced[0]
            prices[token] = price

    best: dict[tuple[str, str], dict] = {}
    for pair, candidates in states.items():
        ranked = []
        for st in candidates:
            reserve_usd_sum = sum(st["reserves"][sym] * prices.get(sym, Decimal(0)) for sym in st["reserves"])
            ranked.append((reserve_usd_sum, st))
        ranked.sort(key=lambda x: x[0], reverse=True)
        if ranked:
            best[pair] = ranked[0][1]
    return best, prices


def load_edge(collateral: str, loan: str, path: pathlib.Path) -> dict:
    rows = []
    with path.open() as f:
        for row in csv.DictReader(f):
            if row["collateral_symbol"] == collateral and row["loan_symbol"] == loan:
                rows.append(row)
    if not rows:
        raise ValueError(f"No Morpho edge {collateral}->{loan}")
    return max(rows, key=lambda r: float(r["borrow_usd"]))


def fmt_usd(x: Decimal) -> str:
    return f"{float(x):,.0f}"


def fmt_pct(x: Decimal) -> str:
    pct = 100 * x
    if Decimal(0) < pct < Decimal("0.01"):
        return "<0.01\\%"
    return f"{float(pct):.2f}\\%"


def fmt_gain(x: Decimal) -> str:
    if Decimal(0) < x < Decimal("0.1"):
        return "<0.1"
    return f"{float(x):.1f}"


def main() -> None:
    root = pathlib.Path(__file__).resolve().parents[2]
    outdir = root / "artifacts" / "impact_calibration"
    outdir.mkdir(parents=True, exist_ok=True)
    active_edges = root / "artifacts" / "morpho_snapshot" / "active_edges.csv"

    block = rpc("eth_blockNumber", [])
    block_int = int(block, 16)
    best_pools, prices = find_best_pools(block)

    rows = []
    for collateral, loan in CYCLE_EDGES:
        edge = load_edge(collateral, loan, active_edges)
        pair = tuple(sorted((collateral, loan)))
        pool = best_pools[pair]
        collateral_reserve_token = pool["reserves"][collateral]
        collateral_reserve_usd = collateral_reserve_token * prices[collateral]
        collateral_usd = Decimal(str(edge["collateral_usd"]))
        sale_fracs = {}
        for frac in SALE_FRACTIONS:
            f = (frac * collateral_usd) / collateral_reserve_usd
            sale_fracs[str(frac)] = {
                "reserve_fraction": str(f),
                "marginal_gain_eta_1pct": str((Decimal(2) * f) / Decimal("0.01")),
                "execution_gain_eta_1pct": str(f / Decimal("0.01")),
            }
        rows.append(
            {
                "collateral": collateral,
                "loan": loan,
                "market_id": edge["marketId"],
                "borrow_usd": str(Decimal(str(edge["borrow_usd"]))),
                "collateral_usd": str(collateral_usd),
                "uniswap_pair": "/".join(pair),
                "pool": pool["pool"],
                "fee": pool["fee"],
                "block": block_int,
                "collateral_price_usd": str(prices[collateral]),
                "collateral_virtual_reserve": str(collateral_reserve_token),
                "collateral_virtual_reserve_usd": str(collateral_reserve_usd),
                "sale_fracs": sale_fracs,
            }
        )

    summary = {
        "rpc_url": RPC_URL,
        "block": block_int,
        "cycle": ["USDC", "WBTC", "WETH", "USDC"],
        "prices_usd": {k: str(v) for k, v in prices.items()},
        "eta_values": [str(x) for x in ETA_VALUES],
        "sale_fractions": [str(x) for x in SALE_FRACTIONS],
        "rows": rows,
        "note": "Stress calibration only; does not assert oracle transmission or actual liquidation.",
    }
    (outdir / "summary.json").write_text(json.dumps(summary, indent=2))

    with (outdir / "edge_stress.csv").open("w", newline="") as f:
        fieldnames = [
            "collateral",
            "loan",
            "borrow_usd",
            "collateral_usd",
            "pool",
            "fee",
            "block",
            "collateral_virtual_reserve_usd",
            "f_1pct_sale",
            "f_5pct_sale",
            "marginal_gain_eta_1pct_1pct_sale",
            "marginal_gain_eta_1pct_5pct_sale",
        ]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "collateral": row["collateral"],
                    "loan": row["loan"],
                    "borrow_usd": row["borrow_usd"],
                    "collateral_usd": row["collateral_usd"],
                    "pool": row["pool"],
                    "fee": row["fee"],
                    "block": row["block"],
                    "collateral_virtual_reserve_usd": row["collateral_virtual_reserve_usd"],
                    "f_1pct_sale": row["sale_fracs"]["0.01"]["reserve_fraction"],
                    "f_5pct_sale": row["sale_fracs"]["0.05"]["reserve_fraction"],
                    "marginal_gain_eta_1pct_1pct_sale": row["sale_fracs"]["0.01"]["marginal_gain_eta_1pct"],
                    "marginal_gain_eta_1pct_5pct_sale": row["sale_fracs"]["0.05"]["marginal_gain_eta_1pct"],
                }
            )

    tex_lines = [
        "% Auto-generated by artifacts/impact_calibration/uniswap_v3_cycle_stress.py",
        f"% Ethereum block {block_int}.",
        "{\\scriptsize",
        "\\begin{tabular}{llrrrr}",
        "\\toprule",
        "Collat. & Debt & Collat. USD & Reserve USD & $f_{1\\%}$ & Gain$_{\\eta=1\\%}$ \\\\",
        "\\midrule",
    ]
    for row in rows:
        collateral_usd = Decimal(row["collateral_usd"])
        reserve_usd = Decimal(row["collateral_virtual_reserve_usd"])
        f1 = Decimal(row["sale_fracs"]["0.01"]["reserve_fraction"])
        gain1 = Decimal(row["sale_fracs"]["0.01"]["marginal_gain_eta_1pct"])
        tex_lines.append(
            f"{row['collateral']} & {row['loan']} & {fmt_usd(collateral_usd)} & "
            f"{fmt_usd(reserve_usd)} & {fmt_pct(f1)} & {fmt_gain(gain1)} \\\\"
        )
    tex_lines += ["\\bottomrule", "\\end{tabular}", "}", ""]
    tex_lines.append(f"Uniswap v3 pools sampled at Ethereum block {block_int}.")
    (outdir / "summary.tex").write_text("\n".join(tex_lines))

    readme = f"""# Uniswap v3 Stress Calibration

This artifact estimates AMM depth for the mainstream Morpho odd-cycle witness:

```text
USDC -- WBTC -- WETH -- USDC
```

The script reads Morpho aggregate market exposures from
`artifacts/morpho_snapshot/active_edges.csv`, queries Uniswap v3 factory/pool
contracts at Ethereum block `{block_int}`, and reports how a small liquidation
stress compares to the active virtual reserve of the collateral token.

This is a market-impact stress calibration only. It does not assert that a
particular lending protocol oracle transmits Uniswap spot moves instantly, and
it does not claim that the reported stress actually occurred.

## Reproduce

```bash
python3 artifacts/impact_calibration/uniswap_v3_cycle_stress.py
```

Outputs:

- `summary.json`: full machine-readable result.
- `edge_stress.csv`: compact CSV.
- `summary.tex`: LaTeX table included by the appendix.
"""
    (outdir / "README.md").write_text(readme)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
