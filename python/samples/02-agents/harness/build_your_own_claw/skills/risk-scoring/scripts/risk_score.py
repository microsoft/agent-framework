# Portfolio risk-scoring script
# Scores concentration risk on a 0-100 scale using the Herfindahl-Hirschman Index (HHI).
#
#   weight_i = position_i / total
#   HHI      = sum(weight_i ^ 2)
#   score    = round(HHI * 100)     # higher = more concentrated = riskier
#
# Usage:
#   python scripts/risk_score.py --position 18518 --position 17201 --position 16177

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(description="Score portfolio concentration risk (0-100).")
    parser.add_argument(
        "--position",
        type=float,
        action="append",
        required=True,
        help="Market value of one holding. Pass once per position.",
    )
    args = parser.parse_args()

    positions = args.position
    if any(p <= 0 for p in positions):
        print(json.dumps({"error": "Each position value must be a positive market value."}))
        return

    total = sum(positions)
    if total <= 0:
        print(json.dumps({"error": "Total portfolio value must be positive."}))
        return

    weights = [p / total for p in positions]
    hhi = sum(w * w for w in weights)
    score = round(hhi * 100)

    if score <= 20:
        band = "Well diversified"
    elif score <= 40:
        band = "Moderately diversified"
    elif score <= 60:
        band = "Concentrated"
    else:
        band = "Highly concentrated"

    print(
        json.dumps({
            "positions": len(positions),
            "score": score,
            "band": band,
            "largest_weight_pct": round(max(weights) * 100, 1),
        })
    )


if __name__ == "__main__":
    main()
