### Motivation and Context

LLM agents are vulnerable to **prompt injection attacks** — malicious instructions in external content (tool results, API responses) that cause data exfiltration or unauthorized actions. 

This PR introduces **FIDES**, a deterministic defense based on **information flow control (IFC)**. Instead of detecting injections, it tracks content provenance via labels and enforces policies — untrusted content can't influence trusted operations, private data can't leak to public channels.

### Description

#### Security Primitives, Middleware & Tools — `_security.py` (single consolidated module)
- **Labels**: `IntegrityLabel` (trusted/untrusted) × `ConfidentialityLabel` (public/private/user_identity)
- **Lattice combination**: most-restrictive-wins via `combine_labels()`
- **Variable indirection**: `ContentVariableStore` replaces untrusted content with opaque `VariableReferenceContent` placeholders — the LLM never sees raw untrusted data
- **`LabelTrackingFunctionMiddleware`** — 3-tier automatic label propagation:
  1. Per-item embedded labels (`additional_properties.security_label`)
  2. Tool-level `source_integrity` declaration
  3. Join of input argument labels (fallback)
- **`PolicyEnforcementFunctionMiddleware`** — blocks or requests approval when context confidentiality exceeds a tool's `max_allowed_confidentiality`
- **`SecureAgentConfig`** — one-line setup wiring middleware, tools, and instructions
- `quarantined_llm` — isolated LLM call (no tools) for safe summarization of untrusted content
- `inspect_variable` — controlled access to hidden variables with label awareness
- All results use `list[Content]` (aligned with upstream `FunctionTool.invoke()`)

#### Framework Integration — `_tools.py`, DevUI
- `FunctionApprovalRequest` content type for human-in-the-loop policy enforcement
- DevUI maps approval requests to interactive approve/reject UI

#### Tests — `test_security.py`
- **115 unit tests** covering label propagation, variable indirection, policy enforcement, quarantine, 3-tier labeling, and edge cases

#### Samples — `python/samples/02-agents/security/`
| Sample | Demonstrates |
|--------|-------------|
| `email_security_example.py` | Integrity-based defense against injection in email content |
| `repo_confidentiality_example.py` | Confidentiality-based data exfiltration prevention |
| `github_mcp_labels_example.py` | Integration with GitHub MCP server labels |

#### Documentation
- `FIDES_DEVELOPER_GUIDE.md` (in `python/samples/02-agents/security/`), `python/samples/02-agents/security/README.md`, `docs/features/FIDES_IMPLEMENTATION_SUMMARY.md`

### Contribution Checklist

- [x] The code builds clean without any errors or warnings
- [x] The PR follows the [Contribution Guidelines](https://github.com/microsoft/agent-framework/blob/main/CONTRIBUTING.md)
- [x] All unit tests pass, and I have added new tests where possible (115 new tests)
- [x] **Is this a breaking change?** No — all changes are additive; security middleware is opt-in via `SecureAgentConfig`
