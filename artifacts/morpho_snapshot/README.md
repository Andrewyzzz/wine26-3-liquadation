# Morpho Snapshot Odd-Cycle Artifact

This directory contains a lightweight reproducibility artifact for the protocol-calibration paragraph and Appendix `app:morpho` of the paper.

## What It Shows

The artifact queries Morpho's public GraphQL API for Ethereum markets ordered by aggregate borrow balance and builds an undirected collateral-loan graph. A market contributes an edge if both its aggregate borrow exposure and aggregate collateral exposure exceed a selected USD threshold.

In the saved snapshot, generated on 2026-06-18 UTC, the graph is non-bipartite at thresholds 0, 100, 1,000, and 10,000 USD. At the 10,000 USD threshold, one odd-cycle witness is:

```text
LBTC -- USDC -- WBTC -- LBTC
```

This is a realized role-reversal witness, not an empirical hardness claim and not a claim about oracle transmission or actual liquidation cascades.

## Files

- `fetch_morpho_snapshot.py`: fetches or reprocesses a Morpho market snapshot, builds threshold graphs, and writes outputs.
- `raw_markets.json`: saved raw API response used by the paper.
- `active_edges.csv`: active collateral-loan edges for all thresholds.
- `odd_cycle.json`: odd-cycle witnesses by threshold.
- `summary.json`: machine-readable summary.
- `summary.tex`: LaTeX table included by the appendix.

## Reproducing From Saved Data

```bash
python3 artifacts/morpho_snapshot/fetch_morpho_snapshot.py \
  --raw-input artifacts/morpho_snapshot/raw_markets.json \
  --thresholds 0,100,1000,10000
```

## Refetching

```bash
python3 artifacts/morpho_snapshot/fetch_morpho_snapshot.py \
  --chain-id 1 \
  --page-size 100 \
  --max-pages 7 \
  --thresholds 0,100,1000,10000 \
  --use-curl
```

The refetch command depends on live API availability and may return a different market state if run later. The paper cites the saved snapshot, not a moving endpoint.
