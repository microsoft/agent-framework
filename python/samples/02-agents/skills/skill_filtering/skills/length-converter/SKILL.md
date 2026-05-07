---
name: length-converter
description: Convert between common length units (miles, km, feet, meters) using a multiplication factor.
---

## Usage

When the user requests a length conversion, run the `scripts/convert.py`
script with `--value <number> --factor <factor>`.

Common factors:
- miles → km: 1.60934
- km → miles: 0.621371
- feet → meters: 0.3048
- meters → feet: 3.28084
