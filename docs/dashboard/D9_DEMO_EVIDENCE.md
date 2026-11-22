# D9 Financial Decision Lab Demo Evidence

**Scope:** Source-backed demonstration values for the local D9 dashboard. These values are educational examples from the frozen historical Test snapshot; they are not current-market estimates or investment advice.

## Selected observation

| Field | Value |
|---|---|
| Split / date / model | Test · 2026-09-25 · ONLINE_SGD (B3) |
| Evaluation ID | `82572c8417041976e1ce540d921e29a5f28c1d5d2a2d953a74c03582e7ca9be2` |
| Replay ID | `3cbf81eb9242d8894d2f67f39065a17ff1ef55a2e098773aead915949ab11b12` |
| Replay run | `0e0cb898-7e75-4fb8-afc0-811dc36b7905` |
| Input snapshot | `45709c99fe13913ccb36f4afb0bc6dd6c168efa743210b00d294a19ab6aa7950` |
| Correlation run | `feat_readiness_20261115_01` |
| Source row | `approved_results/portfolio_risk.csv`, CSV line 1993 |
| Source bundle SHA-256 | `20dff91705ffbb60ab579f5c1f907537015ec2f52be001d5dfd24ea8978ae3f5` |

The row has three `VALID` forecast inputs, `is_corr_ready=True`, `portfolio_status=OK`, and no missing inputs. Stored 20-session correlation proxies are SPY/IEF `0.6751384241`, SPY/GLD `0.5919991904`, and IEF/GLD `0.5074111154`.

## Reproducible scenario values

The source row stores `portfolio_vol_annualized=0.08127699795391094` for the 50/30/20 allocation. Recomputing `sqrt(wᵀΣw)` from that row's stored covariance gives the same value (displayed as **8.1276998% annualized**).

Applying the illustrative 60/20/20 allocation to the same covariance gives **8.4725016% annualized**, a change of **+0.3448018 percentage points** relative to 50/30/20. It is only an allocation comparison under this one historical forecast snapshot; it does not show expected returns, realized portfolio outcomes, or an optimized allocation.

For a UI walkthrough, a presenter may enter a **demonstration-only, user-defined 9% annualized risk budget** and observe the selected-day status. The threshold is not supplied as a research value or default by the product.

## Interpretation limits

- The forecast target is forward realized volatility (RV5) over the next five XNYS sessions. The displayed portfolio value remains annualized volatility.
- Correlations are stored historical 20-session proxies, not forecasts of future correlations.
- Historical point-in-time source availability is not verified. The replay is simulated and frozen; it is not a live estimate.
- The scenario control recalculates against stored covariance only. It does not refit B3 or represent rebalancing/backtesting.
