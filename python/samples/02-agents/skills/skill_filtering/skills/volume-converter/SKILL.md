---
name: volume-converter
description: Convert between gallons and liters using a conversion factor.
---

## Usage

When the user requests a volume conversion:
1. Run the `scripts/convert.py` script with `--value <number> --factor <factor>`
2. Use factor 3.78541 for gallons → liters, or 0.264172 for liters → gallons
3. Present the converted value clearly with both units
