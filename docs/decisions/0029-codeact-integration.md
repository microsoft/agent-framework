---
status: proposed
contact: eavanvalkenburg
date: 2026-04-07
deciders: TBD
consulted:
informed:
---

# CodeAct integration through backend-specific context providers and an `execute_code` tool

## Introduction

**CodeAct** is a pattern in which the model writes executable code — rather than emitting a fixed function-call JSON schema — to plan, transform data, and orchestrate tool calls inside a single sandbox invocation. Instead of requiring a separate model round-trip for every tool call, conditional branch, or data transformation, the model produces a short program that runs in a controlled runtime, calls host-provided tools through a `call_tool(...)` bridge, and returns structured results. This reduces latency, lowers token cost, and lets the model express richer multi-step logic that is difficult to capture in a flat tool-call sequence.

Throughout this ADR, **CodeAct** is the primary term. **Code mode** and **programmatic tool calling** refer to the same capability.

## Context and Problem Statement

We need an architecture design that supports CodeAct in both Python and .NET. This is a necessary capability for the current generation of long-running agents, which need to plan, iterate, transform tool outputs, and execute bounded code inside a controlled runtime — for example, filtering a large result set, computing derived values, or chaining several tool calls with conditional logic — instead of requiring a separate model round-trip for each of those steps. The design should preserve the same behavioral contract across SDKs, but it does not need to use the same internal extension point in each runtime. We also want to standardize on Hyperlight as the initial backend, using the existing Python package and an anticipated .NET binding package once it is available.

Throughout this ADR, **CodeAct** is the primary term. **Code mode** and **programmatic tool calling** refer to the same capability. This ADR uses **CodeAct** consistently.

Model-generated code is treated as untrusted relative to the host process. This ADR assumes the selected backend provides the primary isolation boundary, while the framework is responsible for configuring approvals and capabilities, integrating telemetry, and translating outputs and failures into framework-native shapes. If a backend cannot provide isolation appropriate for its trust model, it is not a suitable CodeAct backend.

The core design question is: **where should CodeAct integrate into the agent pipeline so that both SDKs can offer the same functionality without invasive changes to their core function-calling loops?**

## Decision Drivers

- CodeAct must shape the model-facing surface before model invocation, not only after the model has already chosen tools.
- The design should let users control which tools are available through CodeAct and which remain regular tools only.
- The design must preserve existing session, approval, telemetry, and tool invocation behavior as much as possible.
- The design should define the minimum cross-SDK telemetry and failure semantics for `execute_code`, so Python and .NET do not diverge on basic observability or error handling.
- The design must fit naturally into the extension points that already exist in each SDK.
- The design must be safe for concurrent runs and must not rely on mutating shared agent configuration during invocation.
- The chosen structure should allow multiple backend-specific providers to fit under the same conceptual design over time, even though Hyperlight is the initial target.
- The abstraction should not assume that every backend is a VM-style sandbox; alternative execution models such as Pydantic's Monty should also fit.
- The design should allow `execute_code` to be reused both as a tool-enabled CodeAct runtime and as a standard code interpreter tool implementation.
- The design should remain open to alternative language/runtime modes, such as JavaScript on Hyperlight, rather than baking the abstraction to Python only.
- The design should provide a portable way to configure sandbox capabilities such as file access and network access, including allow-listed outbound domains.
- Using CodeAct should be optional, and installing its runtime or backend dependencies should also be optional.
- Backend-specific dependencies should be isolated behind a small adapter so SDK code is not tightly coupled to an unstable package surface.

## Considered Options

- **Option 1**: Standardize on context provider-based CodeAct with a shared cross-SDK contract and backend-specific public types
- **Option 2**: Implement CodeAct as a dedicated chat-client decorator/wrapper
- **Option 3**: Integrate CodeAct directly into the function invocation layer/FunctionInvokingChatClient

## Pros and Cons of the Options

### Option 1: Standardize on context provider-based CodeAct with a shared cross-SDK contract and backend-specific public types

This option uses `ContextProvider` in Python and `AIContextProvider` in .NET, but standardizes the public concept and behavior.
In this option, the CodeAct tool set is provider-owned: only tools explicitly configured on the concrete CodeAct provider instance are available inside CodeAct, and the provider exposes direct CRUD-style management for tools, file mounts, and outbound network allow-list configuration rather than requiring a separate runtime setup object.
The agent's direct tool surface remains separate. If a tool should be available both through CodeAct and as a normal direct tool, it is configured in both places.

- Good, because both SDKs already have first-class provider concepts intended for per-invocation context shaping.
- Good, because providers operate before model invocation, which is where CodeAct must add instructions and reshape tools.
- Good, because this lets us preserve existing function invocation behavior rather than rewriting it.
- Good, because slightly different internals are acceptable while the public behavior remains aligned.
- Good, because convenience builder/decorator helpers can still be added later on top of the provider model without changing the core design.
- Good, because backend-specific runtime logic can stay inside concrete provider implementations or internal helpers instead of being forced into a lowest-common-denominator public abstraction.
- Good, because the same provider structure can support either an all-or-nothing tool surface or a mixed side-by-side tool surface.
- Good, because users can keep some tools direct-only while allowing other tools to be used from inside CodeAct.
- Good, because a provider-owned CodeAct tool registry avoids mutating or inferring the agent's direct tool surface and can work consistently in both SDKs.
- Good, because the same conceptual design can remain open to `HyperlightCodeActProvider`, a future `MontyCodeActProvider`, and other backend-specific providers over time.
- Good, because `execute_code` can evolve into multiple backend-specific runtime modes rather than being hard-wired to one Python-plus-tools mode.
- Bad, because the provider indirection adds per-run overhead — snapshotting the tool registry, dispatching lifecycle hooks, and building instructions — that a deeper integration point could skip. In practice this overhead is negligible relative to model inference latency and sandbox startup cost.

### Option 2: Implement CodeAct as a dedicated chat-client decorator/wrapper

This option would introduce a CodeAct-specific chat-client decorator that injects instructions and tools directly into the chat request pipeline.

- Good, because this is a natural fit for .NET's `DelegatingChatClient` pipeline.
- Good, because it can also support advanced custom chat-client stacks.
- Good, because backend-specific runtime selection could be hidden inside the decorator implementation.
- Good, because the decorator could also encapsulate mode-specific instruction shaping for tool-enabled versus standalone interpreter behavior.
- Good, because the decorator can decide per request whether the tool surface is exclusive or mixed.
- Bad, because Python can support this by building a custom layering stack on top of a `Raw...Client` and swapping in a different `FunctionInvocationLayer`, but that composition path is more manual than the .NET `DelegatingChatClient` pipeline.
- Bad, because it duplicates responsibilities already handled by provider abstractions.
- Bad, because it makes CodeAct look more transport-specific than it really is.
- Bad, because swappable backends and reusable interpreter or language modes become coupled to chat-client composition rather than modeled as first-class CodeAct concepts.

### Option 3: Integrate CodeAct directly into the function invocation layer/FunctionInvokingChatClient

This option would push CodeAct into Python's `FunctionInvocationLayer` and .NET's `FunctionInvokingChatClient` or related middleware.

- Good, because it is close to tool execution and can observe concrete tool invocation behavior.
- Good, because function middleware may still be useful later for auxiliary auditing or policy around sandbox-originated tool calls.
- Bad, because this is the wrong layer for constructing the model-facing tool surface and prompt instructions.
- Bad, because it does not naturally control whether the model sees an exclusive CodeAct tool surface or a mixed side-by-side tool surface.
- Bad, because it would still require a second mechanism for hiding normal tools and advertising `execute_code`.
- Bad, because it is a weak fit for standalone interpreter modes where no tool-calling loop is needed.
- Bad, because backend selection and CodeAct mode behavior are orthogonal concerns that do not belong in the function invocation layer.
- Bad, because `.NET` would become more tightly coupled to `FunctionInvokingChatClient`, which sits below the agent framework abstraction and is not the natural cross-SDK design seam.

## Approval Model Options

- **Option A**: Bundled approval for the `execute_code` invocation
- **Option B**: Pre-execution inspection of `call_tool(...)` references before approving `execute_code`
- **Option C**: Nested per-tool approvals during `execute_code`

## Pros and Cons of the Approval Options

### Option A: Bundled approval for the `execute_code` invocation

This option grants approval once, before `execute_code` starts. Provider-owned tool calls made from inside that execution run under the same approval. The effective approval of `execute_code` is determined up front from the provider configuration rather than from inspecting which tools are actually called during execution.

- Good, because it is the simplest model to explain and implement consistently in both SDKs.
- Good, because it fits naturally with long-running CodeAct loops where repeated approval interruptions would be disruptive.
- Good, because it does not require static code analysis before execution begins.
- Good, because it keeps the first release focused on the provider integration rather than a more complex approval engine.
- Bad, because approval is coarse-grained and may cover more activity than the user expected.
- Bad, because it provides less visibility into which provider-owned tools or capabilities will be exercised during the run.

### Option B: Pre-execution inspection of `call_tool(...)` references before approving `execute_code`

This option inspects submitted code for statically discoverable `call_tool("tool_name", ...)` references before execution starts and uses that information to shape the approval request.

- Good, because it can show users more detail up front while still keeping approval at a single pre-execution moment.
- Good, because it matches the common case where tool names are spelled out directly in the generated code.
- Good, because it can coexist with bundled approval as a more informative variant of the same UX.
- Bad, because the analysis is inherently best-effort and cannot reliably predict dynamic behavior.
- Bad, because it requires duplicated parsing or inspection logic that does not replace runtime enforcement.

### Option C: Nested per-tool approvals during `execute_code`

This option requests approval when sandboxed code actually attempts to invoke a provider-owned tool that requires approval.

- Good, because it aligns approval with real behavior rather than predicted behavior.
- Good, because it gives precise visibility into which provider-owned tools are being used.
- Good, because it can allow some tool calls while rejecting others within the same execution.
- Bad, because it interrupts long-running CodeAct flows and can degrade the user experience significantly.
- Bad, because it requires more complex runtime plumbing and approval UX in both SDKs.
- Bad, because repeated approval pauses may make CodeAct less useful for the exact long-running scenarios that motivate this feature.

## Decision Outcomes

### Decision 1: Integration seam and public structure

Chosen option: **Option 1: Standardize on provider-based CodeAct with a shared cross-SDK contract and backend-specific public types**, because it is the only option that maps cleanly to both SDKs, lets us reshape instructions and tools before model invocation, and avoids invasive changes to the existing function invocation loops while still allowing multiple backend-specific providers and multiple runtime modes to fit under the same structure later.

### Decision 2: Initial approval model

Chosen option: **Option A: Bundled approval for the `execute_code` invocation**, because it is the smallest approval model that fits both SDKs, works well for long-running CodeAct flows, and does not force us to standardize a more complex inspection or policy engine in the first release.

This follows the spirit of the current Python tool approval flow, where `FunctionTool` uses `approval_mode="always_require" | "never_require"` and the auto-invocation loop escalates the whole batch when any called tool requires approval.

### Design summary

We standardize the **public concept** of CodeAct across SDKs while allowing each SDK to use the extension point that fits it best.

- Python uses a `ContextProvider`.
- .NET uses an `AIContextProvider`.
- The term **CodeAct context provider** is used throughout this ADR as a design concept, not as a required public base type. Public SDK APIs should prefer concrete backend-specific types such as `HyperlightCodeActProvider` rather than a public abstract `CodeActContextProvider` or a public `CodeActExecutor` parameter.
- CodeAct support should ship as an optional package in each SDK rather than as part of the core package, so users who do not need CodeAct do not take on its installation and dependency footprint. That optional package may still depend on a few small, backward-compatible hooks in the host SDK's core agent pipeline.
- There is no separate runtime setup object in the chosen design. Concrete providers manage their provider-owned CodeAct tool registry, file mounts, and outbound network allow-list configuration directly through CRUD-style methods on the provider itself.
- At a high level, CodeAct is exposed through backend-specific context providers that contribute an `execute_code` tool, own the CodeAct-specific tool registry, and carry backend capability configuration such as filesystem and network access.
- The initial approval model is bundled approval for `execute_code`, using the same `approval_mode="always_require" | "never_require"` vocabulary as regular tools.
- The CodeAct provider exposes a default `approval_mode` for `execute_code`. If the provider default is `always_require`, `execute_code` is always treated as `always_require` regardless of the provider-owned tool registry. If the provider default is `never_require`, the effective approval for `execute_code` is derived from the provider-owned CodeAct tool registry captured for the run.
- If every provider-owned CodeAct tool in that registry has `approval_mode="never_require"`, `execute_code` is treated as `never_require`. If any provider-owned CodeAct tool in that registry has `approval_mode="always_require"`, `execute_code` is treated as `always_require`, even if the generated code may not end up calling that tool.
- Approval is granted before `execute_code` starts, and provider-owned tool calls made from inside that execution run under the same approval.
- Direct-only agent tools do not affect the approval of `execute_code`; only the provider-owned CodeAct tool registry participates in that calculation.
- This approval model is intentionally conservative. If one sensitive provider-owned tool forces `execute_code` to require approval more often than desired, the mitigation is to keep that tool direct-only or split it into a different provider/tool surface rather than trying to infer per-run tool usage up front.
- Configuring filesystem and network capability state on the provider, including adding file mounts or outbound network allow-list entries, is itself the approval for those capabilities in the initial model.
- Each `execute_code` invocation must start from a clean execution state; in-memory variables and other ephemeral interpreter/runtime state must not persist across separate calls. When a provider exposes a workspace, mounted files, or a writable artifact/output area, those files are the supported persistence mechanism across calls and are treated as external state rather than interpreter state.
- Mutating the provider's tool registry or capability configuration while a run is in flight is allowed, but it only affects subsequent runs. Provider implementations must snapshot the effective state for each run and synchronize concurrent access so shared provider instances remain safe across concurrent runs.
- The minimum cross-SDK telemetry contract is that `execute_code` is traced as a normal tool invocation nested inside the surrounding agent run, and provider-owned tool calls made from inside CodeAct continue to emit ordinary tool-invocation telemetry. Backend-specific resource metrics are optional extensions, not a required new top-level cross-SDK event model.
- Timeout, out-of-memory, backend crash, and similar sandbox failures are all execution failures of `execute_code` and should surface as structured error results rather than backend-specific public DTOs. Partial textual or file outputs may be returned only when the backend can report them unambiguously; callers must not rely on partial-output recovery as a portable guarantee.
- The provider-based structure preserves room for future pre-execution inspection and nested per-tool approvals if later experience shows they are needed.
- Concrete backend-specific providers may still use small SDK-local helpers or adapters internally, but that split is an implementation detail rather than a public API requirement.

Detailed language-specific implementation notes are specified in:

- [Python implementation](../features/code_act/python-implementation.md)
- [.NET implementation](../features/code_act/dotnet-implementation.md)

### Minimal core hooks required by the optional package

CodeAct remains optional at the package level, but the optional package depends on a small number of hooks that must live in the host SDK because the agent pipeline owns model invocation and per-run tool resolution.

- Python depends on the existing `ContextProvider` lifecycle, `SessionContext.extend_instructions(...)`, `SessionContext.extend_tools(...)`, per-run runtime tool access via `SessionContext.options["tools"]`, and the shared `ApprovalMode` vocabulary used by `FunctionTool`.
- .NET depends on the existing `AIContextProvider` seam, agent/runtime support for applying providers before model invocation, and the existing chat-client or function-invocation seams that concrete implementations use to contribute `execute_code`.

These hooks are backward-compatible because they only expose or forward per-run state that core already owns. Behavior changes only when a concrete CodeAct provider opts in and uses them.

### Concrete provider implementation contract

The design does not require a public abstract `CodeActContextProvider` base class, but it does require a stable implementation contract for concrete providers.

- Concrete providers should expose a standard capability surface at construction time, with SDK-appropriate naming for:
  - approval mode
  - workspace root
  - file mounts
  - allowed outbound targets plus any per-target method or policy restrictions needed by the backend
- Separate public `filesystem_mode` / `network_mode` flags are not required by the cross-SDK contract. Filesystem access may be disabled implicitly until a workspace or file mounts are configured, and outbound network may be disabled implicitly until an allow-list or equivalent outbound policy entry is configured.
- Concrete providers should expose direct CRUD-style methods for managing the provider-owned CodeAct tool registry, file mounts, and outbound network allow-list configuration, rather than requiring callers to construct a separate runtime setup object.
- Concrete providers should implement their host SDK's provider lifecycle hooks to:
  - build CodeAct instructions,
  - add `execute_code`,
  - snapshot the effective CodeAct tool registry and capability settings for the run,
  - compute the effective approval requirement for `execute_code`,
  - configure file access and network access for the backend,
  - prepare or restore execution state,
  - execute code,
  - and translate backend output into framework-native content.
- Any internal abstract/helper surface shared by multiple concrete providers should standardize responsibilities for:
  - instruction construction,
  - file-access configuration,
  - network-access configuration,
  - environment preparation/restoration,
  - code execution,
  - and output-to-content conversion.
- Backend execution output should reuse existing framework-native content/message primitives rather than introducing backend-specific public result DTOs.

## More Information

### Related artifacts

- Python implementation: [`docs/features/code_act/python-implementation.md`](../features/code_act/python-implementation.md)
- .NET implementation: [`docs/features/code_act/dotnet-implementation.md`](../features/code_act/dotnet-implementation.md)
- Python provider/session APIs: [`python/packages/core/agent_framework/_sessions.py`](../../python/packages/core/agent_framework/_sessions.py)
- Python function invocation loop: [`python/packages/core/agent_framework/_tools.py`](../../python/packages/core/agent_framework/_tools.py)
- .NET context provider abstraction: [`dotnet/src/Microsoft.Agents.AI.Abstractions/AIContextProvider.cs`](../../dotnet/src/Microsoft.Agents.AI.Abstractions/AIContextProvider.cs)
- .NET agent integration for context providers: [`dotnet/src/Microsoft.Agents.AI/ChatClient/ChatClientAgent.cs`](../../dotnet/src/Microsoft.Agents.AI/ChatClient/ChatClientAgent.cs)
- Optional .NET chat-client provider decorator: [`dotnet/src/Microsoft.Agents.AI/AIContextProviderDecorators/AIContextProviderChatClient.cs`](../../dotnet/src/Microsoft.Agents.AI/AIContextProviderDecorators/AIContextProviderChatClient.cs)
- .NET function invocation middleware seam: [`dotnet/src/Microsoft.Agents.AI/FunctionInvocationDelegatingAgentBuilderExtensions.cs`](../../dotnet/src/Microsoft.Agents.AI/FunctionInvocationDelegatingAgentBuilderExtensions.cs)

### Related decisions

- [0015-agent-run-context](0015-agent-run-context.md)
- [0016-python-context-middleware](0016-python-context-middleware.md)
