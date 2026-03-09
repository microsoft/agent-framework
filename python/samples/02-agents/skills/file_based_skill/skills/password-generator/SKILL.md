---
name: password-generator
description: Generate secure passwords using a Python script. Use when asked to create passwords or credentials.
---

# Password Generator

This skill generates secure passwords using a Python script.

## Usage

When the user requests a password:
1. First, review `references/PASSWORD_GUIDELINES.md` to determine the recommended password length and character sets for the user's use case
2. Run the `scripts/generate.py` script with the required `--length <number>` argument (e.g. `--length 24`)
3. Present the generated password clearly
