# On-demand development tools

The `requirements-*.txt` files pin development tools that run on one Python
version only. Tools needed by tests across the supported Python matrix remain
in the root `dev` dependency group so the same environment can be exercised on
every version.

- `requirements-quality.txt` contains Ruff.
- `requirements-typing.txt` contains the type checkers used by code-quality
  jobs.
- `requirements-api-compatibility.txt` contains the isolated Griffe pin used
  when checking untrusted pull-request source.
- The `tool-runtime`, `tool-hooks`, and `tool-markdown` dependency groups in
  `pyproject.toml` centrally pin tools that Poe or repository hooks can select
  directly by group.

Run contributor tasks through the cross-version Poe dependency:

```bash
uv run poe check
```

Single-version commands add the relevant bundle:

```bash
uv run --locked --with-requirements tooling/requirements-typing.txt pyright
uv run --group tool-hooks prek run -a
```

Use `uv run poe upgrade-dev-dependency-pins` to refresh exact pins in these
files together with development dependency groups.
