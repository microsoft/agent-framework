# Risk-scoring guide (illustrative)

This skill scores **concentration risk** — how much a portfolio depends on its largest positions —
on a 0-100 scale, where higher means riskier.

## How the score is built

1. Convert each position to a weight: `weight = position_value / total_value`.
2. Compute the Herfindahl-Hirschman Index (HHI): `HHI = sum(weight^2)`.
   - A perfectly even portfolio of *n* holdings has `HHI = 1/n` (low).
   - A single-stock portfolio has `HHI = 1` (maximum concentration).
3. Scale to 0-100: `score = round(HHI * 100)`.

## Score bands

| Score   | Band               | Interpretation                                  |
|---------|--------------------|-------------------------------------------------|
| 0-20    | Well diversified   | No single holding dominates.                    |
| 21-40   | Moderately diversified | Some tilt, but broadly spread.              |
| 41-60   | Concentrated       | A few positions carry most of the risk.         |
| 61-100  | Highly concentrated| Heavily dependent on one or two positions.      |

Also watch the **largest single-position weight**: above ~25% is usually worth flagging regardless
of the overall score.

This measures concentration only — it ignores volatility, correlation, sector exposure, and leverage,
so it is a starting point, not a verdict.
