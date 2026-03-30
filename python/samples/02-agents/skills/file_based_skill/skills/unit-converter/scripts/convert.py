# Unit conversion script
# Converts a value using a multiplication factor: result = value × factor
#
# Usage:
#   python scripts/convert.py --value 26.2 --factor 1.60934
#   python scripts/convert.py --value 75 --factor 2.20462

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Convert a value using a multiplication factor.",
        epilog="Examples:\n"
        "  python scripts/convert.py --value 26.2 --factor 1.60934\n"
        "  python scripts/convert.py --value 75 --factor 2.20462",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--value", type=float, required=True, help="The numeric value to convert.")
    parser.add_argument("--factor", type=float, required=True, help="The conversion factor from the table.")
    args = parser.parse_args()
    result = round(args.value * args.factor, 4)
    print(json.dumps({"value": args.value, "factor": args.factor, "result": result}))


if __name__ == "__main__":
    main()
