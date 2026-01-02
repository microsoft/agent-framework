---
applyTo: '**/agent-framework/python/**'
---
- Use `uv run` as the main entrypoint for running Python commands with all packages available.
- Use `uv run poe <task>` for development tasks like formatting (`fmt`), linting (`lint`), type checking (`pyright`, `mypy`), and testing (`test`).
- Use `uv run --directory packages/<package> poe <task>` to run tasks for a specific package.
- Read [DEV_SETUP.md](../../DEV_SETUP.md) for detailed development environment setup and available poe tasks.
- Read [CODING_STANDARD.md](../../CODING_STANDARD.md) for the project's coding standards and best practices.
- When verifying logic with unit tests, run only the related tests, not the entire test suite.
- For new tests and samples, review existing ones to understand the coding style and reuse it.
- When generating new functions, always specify the function return type and parameter types.
- Do not use `Optional`; use `Type | None` instead.
- Before running any commands to execute or test the code, ensure that all problems, compilation errors, and warnings are resolved.
- When formatting files, format only the files you changed or are currently working on; do not format the entire codebase.
- Do not mark new tests with `@pytest.mark.asyncio`.
- If you need debug information to understand an issue, use print statements as needed and remove them when testing is complete.
- Avoid adding excessive comments.
- When working with samples, make sure to update the associated README files with the latest information. These files are usually located in the same folder as the sample or in one of its parent folders.

Sample structure:
1. Copyright header: `# Copyright (c) Microsoft. All rights reserved.`
2. Required imports.
3. Short description about the sample: `"""This sample demonstrates..."""`
4. Helper functions.
5. Main functions that demonstrate the functionality. If it is a single scenario, use a `main` function. If there are multiple scenarios, define separate functions and add a `main` function that invokes all scenarios.
6. Place `if __name__ == "__main__": asyncio.run(main())` at the end of the sample file to make the example executable.
