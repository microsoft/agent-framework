# Microsoft.Agents.AI.AzureAI.Persistent

Provides integration between the Microsoft Agent Framework and Azure AI Agents Persistent (`Azure.AI.Agents.Persistent`).

## ⚠️ Known Compatibility Limitation

The underlying `Azure.AI.Agents.Persistent` package (currently 1.2.0-beta.9) targets `Microsoft.Extensions.AI.Abstractions` 10.1.x and references types that were renamed in 10.4.0 (e.g., `McpServerToolApprovalResponseContent` → `ToolApprovalResponseContent`). This causes `TypeLoadException` at runtime when used with ME.AI 10.4.0+.

**Compatible versions:**

| Package | Compatible Version |
|---|---|
| `Azure.AI.Agents.Persistent` | 1.2.0-beta.9 (targets ME.AI 10.1.x) |
| `Microsoft.Extensions.AI.Abstractions` | ≤ 10.3.0 |
| `OpenAI` | ≤ 2.8.0 |

**Resolution:** An updated version of `Azure.AI.Agents.Persistent` targeting ME.AI 10.4.0+ is expected in 1.2.0-beta.10. The upstream fix is tracked in [Azure/azure-sdk-for-net#56929](https://github.com/Azure/azure-sdk-for-net/pull/56929).

**Tracking issue:** [microsoft/agent-framework#4769](https://github.com/microsoft/agent-framework/issues/4769)
