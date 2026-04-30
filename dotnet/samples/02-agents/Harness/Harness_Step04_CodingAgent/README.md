# What this sample demonstrates

A coding-style agent that operates over a real on-disk workspace, with security-first defaults.

Key features showcased:

- **`FileSystemToolProvider`** — exposes both the universal `FileAccess_*` tools and the high-fidelity `fs_*` tools (`fs_view` with line ranges, `fs_edit` unique-match, `fs_multi_edit` atomic batch, `fs_glob`, `fs_grep`, `fs_list_dir`, `fs_move`, `fs_rename`). Inherits from `FileAccessProvider`, so any code that consumes a `FileAccessProvider` continues to work.
- **Sandboxed workspace** — paths are confined to the workspace root. Symlink traversal is rejected and secrets-like paths (`.env*`, `*.pem`, …) are blocked by default.
- **Approval-gated mutations** — `FileAccess_DeleteFile`, `fs_move`, and `fs_rename` are wrapped in `ApprovalRequiredAIFunction`. The harness `ToolApprovalAgent` (added via `.UseToolApproval()`) prompts the user and remembers per-session "always allow" decisions.
- **`TodoProvider` + `AgentModeProvider`** — plan-then-execute workflow with an agent-tracked todo list.
- **Compaction & streaming** — long edit sessions stay within the model's context window.

## Prerequisites

1. An Azure AI Foundry project with a deployed model (e.g., `gpt-5.4`).
2. Azure CLI installed and authenticated (`az login`).

## Environment variables

```bash
# Required
export AZURE_FOUNDRY_OPENAI_ENDPOINT="https://your-project.services.ai.azure.com/openai/v1/"

# Optional (defaults to gpt-5.4)
export AZURE_AI_MODEL_DEPLOYMENT_NAME="gpt-5.4"
```

## Run

```bash
dotnet run --project dotnet/samples/02-agents/Harness/Harness_Step04_CodingAgent
```

## Things to try

- "List the files in the workspace, then summarise what's there."
- "Add a new function `Foo` to `src/calc.cs` and a unit test for it."
- "Rename `notes.md` to `README.md`." (will trigger the approval prompt)
- "Refactor the `Bar` class to extract its logging code into a helper." (uses `fs_grep` + `fs_multi_edit`)

## Decision rule: which provider?

- Use `FileAccessProvider` directly when the backend is in-memory, remote blob storage, or another non-filesystem store.
- Use `FileSystemToolProvider` when you want a real coding-workspace experience on disk: line-range reads, atomic edits, gitignore-aware search, ripgrep, and approval-gated mutations.
