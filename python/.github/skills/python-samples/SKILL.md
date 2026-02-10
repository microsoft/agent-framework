---
name: python-samples
description: >
  Guidelines for creating and modifying sample code in the Agent Framework
  Python codebase. Use this when writing new samples or updating existing ones.
---

# Python Samples

## File Structure

Every sample file follows this order:

1. PEP 723 inline script metadata (if external dependencies needed)
2. Copyright header: `# Copyright (c) Microsoft. All rights reserved.`
3. Required imports
4. Module docstring: `"""This sample demonstrates..."""`
5. Helper functions
6. Main function(s) demonstrating functionality
7. Entry point: `if __name__ == "__main__": asyncio.run(main())`

## External Dependencies

Use [PEP 723](https://peps.python.org/pep-0723/) inline script metadata for
external packages not in the dev environment:

```python
# /// script
# requires-python = ">=3.10"
# dependencies = [
#     "some-external-package",
# ]
# ///
# Run with: uv run samples/path/to/script.py

# Copyright (c) Microsoft. All rights reserved.
```

Do **not** add sample-only dependencies to the root `pyproject.toml` dev group.

## Syntax Checking

```bash
# Check samples for syntax errors and missing imports
uv run poe samples-syntax

# Lint samples
uv run poe samples-lint
```

## Documentation

Samples should be over-documented:

1. Include a README.md in each set of samples
2. Add a summary docstring under imports explaining the purpose and key components
3. Mark code sections with numbered comments:
   ```python
   # 1. Create the client instance.
   ...
   # 2. Create the agent with the client.
   ...
   ```
4. Include expected output at the end of the file:
   ```python
   """
   Sample output:
   User:> Why is the sky blue?
   Assistant:> The sky is blue due to Rayleigh scattering...
   """
   ```

## Guidelines

- **Incremental complexity** — start simple, build up (step1, step2, ...)
- **Getting started naming**: `step<number>_<name>.py`
- When modifying samples, update associated README files
