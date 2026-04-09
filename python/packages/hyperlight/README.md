# agent-framework-hyperlight

Alpha Hyperlight-backed CodeAct integrations for Microsoft Agent Framework.

## Installation

```bash
pip install agent-framework-hyperlight --pre
```

This package depends on `hyperlight-sandbox`, the packaged Python guest, and the
Wasm backend package on supported platforms. If the backend is not published for
your current platform yet, `execute_code` will fail at runtime when it tries to
create the sandbox.

## Public API

- `HyperlightCodeActProvider`
- `HyperlightExecuteCodeTool`
- `FileMount`
- `FileMountInput`

## Notes

- This package is intentionally separate from `agent-framework-core` so CodeAct
  usage and installation remain optional.
- Alpha-package samples live under `packages/hyperlight/samples/`.
- `file_mounts` accepts a single string shorthand, an explicit `(host_path,
  mount_path)` pair, or a `FileMount` named tuple. Use the explicit two-value
  form when the host path differs from the sandbox path.
