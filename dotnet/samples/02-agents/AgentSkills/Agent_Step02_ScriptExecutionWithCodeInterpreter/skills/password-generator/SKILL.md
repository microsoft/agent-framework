---
name: password-generator
description: Generate secure passwords using a Python script. Use when asked to create passwords or credentials.
---

# Password Generator

This skill generates secure passwords using a Python script.

## Usage

When the user requests a password:
1. First, review `references/PASSWORD_GUIDELINES.md` to determine the recommended password length and character sets for the user's use case
2. Load `scripts/generate.py` and adjust its parameters (length, character set) based on the guidelines and user's requirements
3. Execute the script
4. Present the generated password clearly
