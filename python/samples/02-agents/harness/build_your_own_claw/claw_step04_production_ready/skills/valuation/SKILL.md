---
name: valuation
description: Estimate whether a stock looks cheap or expensive using a price-to-earnings (P/E) based fair-value method. Use when the user asks if a stock is over- or under-valued, or for a fair-value / target price.
---

## Usage

When the user asks whether a stock is fairly valued, over-valued, or under-valued:

1. Read `references/valuation-guide.md` to pick a sensible target P/E for the company's sector.
2. Run `scripts/valuation_metrics.py` with the current price, trailing EPS, and the target P/E,
   e.g. `--price 462.97 --eps 11.80 --target-pe 32`.
3. Report the computed P/E, the fair-value estimate, and the percentage upside/downside, then state
   plainly whether the stock looks cheap or expensive on this measure.

Always remind the user that a single P/E heuristic is not investment advice and ignores growth,
debt, and many other factors.
