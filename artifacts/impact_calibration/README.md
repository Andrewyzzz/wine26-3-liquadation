# Uniswap v3 Stress Calibration

This artifact estimates AMM depth for the mainstream Morpho odd-cycle witness:

```text
USDC -- WBTC -- WETH -- USDC
```

The script reads Morpho aggregate market exposures from
`artifacts/morpho_snapshot/active_edges.csv`, queries Uniswap v3 factory/pool
contracts at Ethereum block `25345235`, and reports how a small liquidation
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
