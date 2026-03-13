---
name: unit-converter
description: Convert between common units using a multiplication factor. Use when asked to convert miles, kilometers, pounds, or kilograms.
---

## Usage

When the user requests a unit conversion:
1. First, review `references/CONVERSION_TABLES.md` to find the correct factor
2. Run the `scripts/convert.py` script with `--value <number> --factor <factor>` (e.g. `--value 26.2 --factor 1.60934`)
3. Present the converted value clearly with both units
