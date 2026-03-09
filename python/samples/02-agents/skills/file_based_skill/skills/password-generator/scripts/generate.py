# Password generator script
# Generates a random password with configurable length.
#
# Usage:
#   python scripts/generate.py --length 16
#   python scripts/generate.py --length 24

import argparse
import json
import random
import string
import sys


def generate(length: int) -> str:
    """Generate a random password of the given length."""
    pool = string.ascii_lowercase + string.ascii_uppercase + string.digits + string.punctuation
    return "".join(random.SystemRandom().choice(pool) for _ in range(length))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate a random password.",
        epilog="Examples:\n  python scripts/generate.py --length 16\n  python scripts/generate.py --length 24",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--length",
        type=int,
        required=True,
        help="Password length (required). Must be >= 4.",
    )
    args = parser.parse_args()

    if args.length < 4:
        print("Error: --length must be >= 4. Received: {}.".format(args.length), file=sys.stderr)
        sys.exit(1)

    password = generate(length=args.length)
    print(json.dumps({"password": password, "length": args.length}))


if __name__ == "__main__":
    main()
