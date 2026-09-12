# Valuation metrics script
# Computes a simple price-to-earnings (P/E) based fair-value estimate.
#
#   fair_value = eps * target_pe
#   pe         = price / eps
#   upside     = (fair_value - price) / price
#
# Usage:
#   python scripts/valuation_metrics.py --price 462.97 --eps 11.80 --target-pe 32

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(description="Compute a P/E based fair-value estimate.")
    parser.add_argument("--price", type=float, required=True, help="Current share price.")
    parser.add_argument("--eps", type=float, required=True, help="Trailing earnings per share.")
    parser.add_argument("--target-pe", type=float, required=True, help="Target P/E from the guide.")
    args = parser.parse_args()

    if args.eps <= 0:
        print(json.dumps({"error": "EPS must be positive to compute a P/E ratio."}))
        return

    if args.price <= 0:
        print(json.dumps({"error": "Price must be positive to compute valuation metrics."}))
        return

    if args.target_pe <= 0:
        print(json.dumps({"error": "Target P/E must be positive."}))
        return

    pe = args.price / args.eps
    fair_value = args.eps * args.target_pe
    upside = (fair_value - args.price) / args.price

    if upside > 0.05:
        verdict = "looks cheap"
    elif upside < -0.05:
        verdict = "looks expensive"
    else:
        verdict = "roughly fairly valued"

    print(
        json.dumps({
            "price": round(args.price, 2),
            "eps": round(args.eps, 2),
            "target_pe": round(args.target_pe, 2),
            "pe": round(pe, 2),
            "fair_value": round(fair_value, 2),
            "upside_pct": round(upside * 100, 1),
            "verdict": verdict,
        })
    )


if __name__ == "__main__":
    main()
