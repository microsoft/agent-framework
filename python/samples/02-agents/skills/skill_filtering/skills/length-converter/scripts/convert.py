"""Convert a value by multiplying it with a factor."""

import argparse
import json


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--value", type=float, required=True)
    parser.add_argument("--factor", type=float, required=True)
    args = parser.parse_args()

    result = round(args.value * args.factor, 4)
    print(json.dumps({"value": args.value, "factor": args.factor, "result": result}))


if __name__ == "__main__":
    main()
