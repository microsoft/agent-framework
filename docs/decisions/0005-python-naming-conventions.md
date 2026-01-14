---
status: accepted
contact: eavanvalkenburg
date: 2025-09-04
deciders: markwallace-microsoft, dmytrostruk, peterychang, ekzhu, sphenry
consulted: taochenosu, alliscode, moonbox3, johanste
---

# Python naming conventions and renames (ADR)

## Context and Problem Statement

The project has a public .NET surface and a Python surface. During a cross-language alignment effort the community proposed renames to make the Python surface more idiomatic while preserving discoverability and mapping to the .NET names. This ADR captures the final naming decisions (or the proposed ones), the rationale, and the alternatives considered and rejected.

## Decision drivers

- Follow Python naming conventions (PEP 8) where appropriate (snake_case for functions and module-level variables, PascalCase for classes).
- Preserve conceptual parity with .NET names to make it easy for developers reading both surfaces to correlate types and behaviors.
- Avoid ambiguous or overloaded names in Python that could conflict with stdlib, common third-party packages, or existing package/module names.
- Prefer clarity and discoverability in the public API surface over strict symmetry with .NET when Python conventions conflict.
- Minimize churn and migration burden for existing Python users where backwards compatibility is feasible.

## Principles applied

- Map .NET PascalCase class names to PascalCase Python classes when they represent types.
- Map .NET method/field names that are camelCase to snake_case in Python where they will be used as functions or module-level attributes.
- When a .NET name is an acronym or initialism, use Python-friendly casing (e.g., `Http` -> `HTTP` in classes, but acronyms in function names should be lowercased per PEP 8 where sensible).
- Avoid names that shadow common stdlib modules (e.g., `logging`, `asyncio`) or widely used third-party modules.
- When multiple reasonable Python names exist, prefer the one that communicates intent most clearly to Python users, and record rejected alternatives in the table with justification.

## Renaming table

The table below represents the majority of the naming changes discussed in issue #506. Each row has:
- Original and/or .NET name — the canonical name used in dotnet or earlier Python variants.
- New name — the chosen Python name.
- Status — accepted if the new name differs from the original, rejected if unchanged.
- Reasoning — short rationale why the new name was chosen.
- Rejected alternatives — other candidate new names that were considered and rejected; include the rejected 'new name' values and the reason each was rejected.

| Original and/or .NET name | New name (Python) | Status | Reasoning | Rejected alternatives (as "new name" + reason rejected) |
|---|---|---|---|---|
| AIAgent | AgentProtocol | accepted | The AI prefix is meaningless in the context of the Agent Framework, and the `protocol` suffix makes it very clear that this is a protocol, and not a concrete agent implementation. | <ul><li>AgentLike, not seen in many other places, but was a frontrunner.</li><li>Agent, as too generic.</li><li>BaseAgent/AbstractAgent, it is not a base/ABC class and should not be treated as such.</li></ul> |
| ChatClientAgent | ChatAgent | accepted | Type name is shorter, while it is still clear that a ChatClient is used, also by virtue of the first parameter for initialization. | Agent, as too generic. |
| ChatClient/IChatClient (in dotnet) | ChatClientProtocol | accepted | Keeping this protocol in sync with the AgentProtocol naming. | Similar as AgentProtocol. |
| ChatClientBase | BaseChatClient | accepted | Following convention, serves as base class so, should be named accordingly. | None |
| AITool | ToolProtocol | accepted | In line with other protocols. | Tool, too generic. |
| AIToolBase | BaseTool | accepted | More descriptive than just Tool, while still concise. | AbstractTool/BaseTool, it is not an abstract/base class and should not be treated as such. |
| ChatRole | Role | accepted | More concise while still clear in context. | None |
| ChatFinishReason | FinishReason | accepted | More concise while still clear in context. | None |
| AIContent | BaseContent | accepted | More accurate as it serves as the base class for all content types. | Content, too generic. |
| AIContents | Contents | accepted | This is the annotated typing object that is the union of all concrete content types, so plural makes sense and since this is used as a type hint, the generic nature of the name is acceptable. | None |
| AIAnnotations | Annotations | accepted | In sync with contents | None |
| AIAnnotation | BaseAnnotation | accepted | In sync with contents | None |
| *Mcp* & *Http* | *MCP* & *HTTP* | accepted | Acronyms should be uppercased in class names, according to PEP 8. | None |
| `agent.run_streaming` | `agent.run_stream` | accepted | Shorter and more closely aligns with AutoGen and Semantic Kernel names for the same methods. | None |
| `workflow.run_streaming` | `workflow.run_stream` | accepted | In sync with `agent.run_stream` and shorter and more closely aligns with AutoGen and Semantic Kernel names for the same methods. | None |
| AgentResponse & AgentResponseUpdate | AgentResponse & AgentResponseUpdate | rejected | Rejected, because it is the response to a run invocation and AgentResponse is too generic. | None |
| *Content | * | rejected | Rejected other content type renames (removing `Content` suffix) because it would reduce clarity and discoverability. | Item was also considered, but rejected as it is very similar to Content, but would be inconsistent with dotnet. |
| ChatResponse & ChatResponseUpdate | Response & ResponseUpdate | rejected | Rejected, because Response is too generic. | None |

## Naming guidance
In general Python tends to prefer shorter names, while .NET tends to prefer more descriptive names. The table above captures the specific renames agreed upon, but in general the following guidelines were applied:
- Use [PEP 8](https://peps.python.org/pep-0008/) for generic naming conventions (snake_case for functions and module-level variables, PascalCase for classes).

When mapping .NET names to Python:
- Remove `AI` prefix when appropriate, as it is often redundant in the context of an AI SDK.
- Remove `Chat` prefix when the context is clear (e.g., Role and FinishReason).
- Use `Protocol` suffix for interfaces/protocols to clarify their purpose.
- Use `Base` prefix for base classes that are not abstract but serve as a common ancestor for internal implementations.
- When readability improves while it is still easy to understand what it does and how it maps to the .NET name, prefer the shorter name.
