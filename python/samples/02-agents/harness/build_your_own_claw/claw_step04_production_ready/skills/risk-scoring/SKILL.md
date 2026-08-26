---
name: risk-scoring
description: Score how concentrated and risky a portfolio is on a 0-100 scale from its position weights. Use when the user asks how risky their portfolio is, whether it is too concentrated, or for a diversification check.
---

## Usage

When the user asks about portfolio risk or concentration:

1. Read `references/risk-bands.md` to understand the score bands and what drives them.
2. Compute each holding's market value (shares × price) — use the `get_stock_price` tool for current
   prices if you do not already have them.
3. Run `scripts/risk_score.py` with one `--position VALUE` argument per holding,
   e.g. `--position 18518 --position 17201 --position 16177`.
4. Report the 0-100 score, the band it falls in, and the largest single-position weight, then suggest
   (in general terms) whether the portfolio looks well diversified or concentrated.

Remind the user this is a crude concentration measure, not a complete risk model, and not advice.
