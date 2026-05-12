# Architecture Elevation Assessment

**Date**: 2026-05-12
**Target**: source.md
**Mode**: advisory
**Verdict**: Frame correct (with grounded constraint)

## Phase 0 — Concerning Abstractions

The design concern is: "Replace reflection-based `ReflectingExecutor<T>` with a compile-time source generator that discovers `[MessageHandler]` attributed methods and generates `ConfigureProtocol` implementations."

The concern exists because there are two parallel mechanisms for binding message handlers to executor route tables — one runtime-reflection-based, one compile-time-source-generated — and the design requests completing and validating the compile-time path so the reflection path can be deprecated and removed.

**Q0.1 — Concerning abstractions:**

| Abstraction | file:line | Would removal eliminate the concern? (YES/NO + why) | Simpler system lacking this pattern |
|---|---|---|---|
| `ReflectingExecutor<TExecutor>` | `Reflection/ReflectingExecutor.cs:23-27` | NO — removing it is the goal of this design, not the source of the concern; removing it alone does not eliminate the need for handler binding, which must be served by either the generator or manual overrides | A system where users hand-write `ConfigureProtocol` overrides (no codegen, no reflection). This system lacks the concern but imposes boilerplate. |
| `IMessageHandler<TMessage>` / `IMessageHandler<TMessage, TResult>` | `Reflection/IMessageHandler.cs:19,44` | NO — these are the interface marker mechanism for reflection discovery; removing them does not eliminate the need for route binding, only removes one discovery strategy | Same hand-written system above. |
| `RouteBuilderExtensions.GetHandlerInfos()` (reflection scanner) | `Reflection/RouteBuilderExtensions.cs:47-78` | NO — this is the runtime reflection scanner that implements `ReflectingExecutor`'s discovery; removing it only shifts binding to another mechanism (generator or manual) | Same. |
| `MessageHandlerInfo` (reflection binding model) | `Reflection/MessageHandlerInfo.cs:16-149` | NO — this is the runtime data model for reflected handlers; removing it does not eliminate the need for handler metadata, which is now captured in `HandlerInfo` (generator model) at compile time | Same. |
| `ValueTaskTypeErasure` | `Reflection/ValueTaskTypeErasure.cs` (file exists per listing) | NO — this is a helper for runtime type erasure of `ValueTask<T>` return values; the generator eliminates the need by emitting statically-typed delegate references | Same. |

No abstraction in the list, if removed alone, would eliminate the concern. The concern is structural: executors must bind message-type-to-handler mappings, and the question is at what phase (compile-time vs. runtime) this binding occurs. Both reflection and source generation are strategies for the same invariant.

**Q0.2 — Counterfactual:** For each abstraction above, the answer is NO. Removing any single abstraction shifts the implementation burden but does not eliminate the fundamental concern (handler route registration).

**Q0.3 — Simpler-system comparison:** A system where users hand-write `ConfigureProtocol` overrides (which is already supported: `Executor.ConfigureProtocol` at `Executor.cs:216` is abstract and can be manually implemented) lacks the concern entirely. That system trades automation for boilerplate. The source generator is an optimization of that simpler system — not a new abstraction layer.

**Conclusion:** No Candidate 0 (frame-level lift) exists. The concern is not caused by an abstraction that could be removed; it is caused by the desire to automate a fundamentally necessary step (binding handlers to routes).

## Ownership Map

| Layer | Location (file:line) | Enforcement | Policy carried |
|---|---|---|---|
| Abstract contract | `Executor.cs:216` — `protected abstract ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)` | mechanical (compile-time: abstract forces override) | Every Executor subclass must declare its protocol |
| Source generator — syntax detection | `ExecutorRouteGenerator.cs:33-37` — `ForAttributeWithMetadataName` predicate filtering `MethodDeclarationSyntax` with `[MessageHandler]` | mechanical (compile-time: Roslyn pipeline) | Only methods annotated with `[MessageHandler]` are candidates |
| Source generator — semantic validation | `SemanticAnalyzer.cs:47-103` — `AnalyzeHandlerMethod()` | mechanical (compile-time: emits error diagnostics that fail build) | Handler must have valid signature: `(T, IWorkflowContext[, CT])`, non-static, valid return type |
| Source generator — class validation | `SemanticAnalyzer.cs:110-189` — `CombineHandlerMethodResults()` | mechanical (compile-time: error diagnostics) | Class must be `partial`, derive from `Executor`, not already define `ConfigureProtocol` |
| Source generator — code emission | `SourceBuilder.cs:27-127` — `Generate()` | mechanical (compile-time: emits compilable C# partial class) | Generated `ConfigureProtocol` override chains `AddHandler<T>` / `AddHandler<T,R>` calls correctly |
| Source generator — diagnostic descriptors | `DiagnosticDescriptors.cs:34-107` — 7 descriptors `MAFGENWF001-007` | mechanical (compile-time: build errors/warnings) | Invalid handler signatures, non-partial classes, non-Executor classes, static handlers all reported |
| Attribute definition — `[MessageHandler]` | `Attributes/MessageHandlerAttribute.cs:48-70` | instruction (attribute signals intent, enforced by generator) | Method is a handler; optional `Yield`/`Send` type arrays |
| Attribute definition — `[SendsMessage]` | `Attributes/SendsMessageAttribute.cs:32-49` | instruction (attribute signals intent, enforced by generator + `ProtocolBuilder`) | Executor declares it sends message type T |
| Attribute definition — `[YieldsOutput]` | `Attributes/YieldsOutputAttribute.cs:32-49` | instruction (attribute signals intent, enforced by generator + `ProtocolBuilder`) | Executor declares it yields output type T |
| Runtime route registration | `RouteBuilder.cs:51-89` — `AddHandlerInternal()` | runtime (throws `ArgumentException` for duplicate handler types) | Each message type maps to exactly one handler |
| Runtime protocol building | `ProtocolBuilder.cs:156-173` — `Build()` | runtime (constructs `ExecutorProtocol` from declared types + routes) | Send/Yield type sets + route table are frozen at build time |
| Runtime protocol validation | `ExecutorProtocol` at `Executor.cs:127-158` — `CanHandle()`, `CanOutput()` | runtime (returns bool, used for routing decisions) | Only declared types can be sent/yielded |
| Legacy reflection discovery | `ReflectingExecutor.cs:36-75` — `ConfigureProtocol()` override | runtime (reflection-based discovery of `IMessageHandler<T>` interfaces) | DUPLICATED: Same invariant as source generator, but via runtime reflection |
| Legacy interface reflection | `RouteBuilderExtensions.cs:47-78` — `GetHandlerInfos()` | runtime (scans `TExecutor` type for `IMessageHandler<>` interfaces) | DUPLICATED: discovers handlers at runtime via interface scanning |
| Legacy `[Obsolete]` markers | `ReflectingExecutor.cs:21-22`, `IMessageHandler.cs:17-18,42-43` | advisory (compiler warning, not error) | Signals migration path but does not prevent usage |

**Ownership duplication flag:** The handler-to-route binding invariant is carried in TWO locations:
1. Source generator pipeline (`ExecutorRouteGenerator` + `SemanticAnalyzer` + `SourceBuilder`) — compile-time, mechanical
2. Reflection pipeline (`ReflectingExecutor` + `RouteBuilderExtensions` + `MessageHandlerInfo`) — runtime, runtime

This is the explicit design intent: the source generator replaces the reflection pipeline. The `[Obsolete]` markers signal this transition but do not enforce it (advisory level).

## Elimination Candidates

### Candidate 1: Complete ReflectingExecutor Removal (Runtime-to-Compile-Time Shift)

- **Altitude**: Abstraction removal — delete entire reflection-based handler discovery
- **Target boundary**: `Reflection/` directory: `ReflectingExecutor.cs`, `IMessageHandler.cs`, `RouteBuilderExtensions.cs`, `MessageHandlerInfo.cs`, `ReflectionExtensions.cs`, `ValueTaskTypeErasure.cs`
- **Invariant carried**: Handler-to-route binding is performed exclusively at compile time via source generator
- **Deletion ledger**:
  - `Reflection/ReflectingExecutor.cs` (77 lines) — entire file
  - `Reflection/IMessageHandler.cs` (55 lines) — entire file
  - `Reflection/RouteBuilderExtensions.cs` (79 lines) — entire file
  - `Reflection/MessageHandlerInfo.cs` (149 lines) — entire file
  - `Reflection/ReflectionExtensions.cs` (54 lines) — entire file
  - `Reflection/ValueTaskTypeErasure.cs` (file exists per listing) — entire file
  - Total: ~6 files, ~414+ lines removed
- **Addition ledger**:
  - Migration documentation (not counted as code)
  - Potential test updates for consumers that inherit from `ReflectingExecutor<T>`
  - No new types/methods/interfaces required — the generator already exists and handles all cases
- **Category elimination**: YES — eliminates the entire category of "runtime reflection-based handler discovery" decisions. No more `DynamicallyAccessedMembers` trimmer annotations, no more runtime type scanning, no more `MethodInfo.Invoke`.

**Subtraction gate:**
- Dimension 1 (artifacts): ~414+ lines deleted, ~0 lines added. PASS.
- Dimension 2 (categories): Eliminates entire runtime reflection handler discovery category. PASS.

**Gate result: PASS (both dimensions)**

### Candidate 2: Promote `[Obsolete]` from Warning to Error

- **Altitude**: Compile-time constraint (change `error: false` to `error: true` on `[Obsolete]` attributes)
- **Target boundary**: `ReflectingExecutor.cs:21-22`, `IMessageHandler.cs:17-18,42-43`
- **Invariant carried**: Usage of reflection-based path is a compile error, not a warning
- **Deletion ledger**: Change 3 attribute instances from `error: false` to `error: true` (or add `error: true` where not present). Note: current `ReflectingExecutor` `[Obsolete]` does not specify `error:` explicitly (defaults to `false`). `IMessageHandler` `[Obsolete]` also does not specify `error:`.
- **Addition ledger**: No new types or files. Three one-line edits.
- **Category elimination**: NO — does not eliminate a category of runtime decision; merely escalates severity

**Subtraction gate:**
- Dimension 1 (artifacts): 0 deletions, 0 additions (modifications only). FAIL.
- Dimension 2 (categories): Does not eliminate a category. FAIL.

**Gate result: FAIL (neither dimension)**

## Self-Challenge

### Candidate 1: Complete ReflectingExecutor Removal

| # | Question | Rejection succeeds? | Grounding provided | Grounding passes? |
|---|---|---|---|---|
| Q1 | Does the target boundary exist in this codebase's topology? | NO (rejection fails) | `Reflection/` directory contains all 6 files listed; verified via `find` in codebase-snapshot.md section 1 and direct reads of `ReflectingExecutor.cs`, `IMessageHandler.cs`, `RouteBuilderExtensions.cs`, `MessageHandlerInfo.cs`, `ReflectionExtensions.cs` | YES — all files exist at stated paths |
| Q2 | Does the language/framework/runtime support the proposed invariant? | NO (rejection fails) | C# source generators via `IIncrementalGenerator` (Roslyn 4.4.0+) are fully supported; the generator already exists and is operational at `ExecutorRouteGenerator.cs:22`. The `[Generator]` attribute and `ForAttributeWithMetadataName` API are used. | YES — runtime and framework support verified |
| Q3 | Does an ADR or user-signed decision decline this migration? | NO (rejection fails) | codebase-snapshot.md section "Decision History > ADRs" states: "No ADRs found specifically addressing the source generator or Workflows architecture." The source.md design decisions (confirmed) explicitly state: "Migration: Clean break - requires direct Executor inheritance (not ReflectingExecutor<T>)". The `[Obsolete]` markers on `ReflectingExecutor` and `IMessageHandler` are themselves user-signed decisions approving deprecation. | YES — no ADR blocks; design decisions actively support removal |
| Q4 | Does the lift create a worse defect class? | YES (rejection succeeds — partially) | Removing `ReflectingExecutor<T>` before all downstream consumers have migrated would break binary compatibility. The `[Obsolete]` attribute with `error: false` currently allows a grace period. If external consumers (NuGet package users) still reference `ReflectingExecutor<T>`, removal is a breaking change (assembly-level `TypeLoadException` at runtime for consumers compiled against the old API). This is a **worse defect class**: upgrading the NuGet package would cause runtime failures rather than compile-time warnings. | YES — binary compatibility concern is real for published packages |
| Q5 | Does the lift step OUTSIDE the concern's named domain? | NO (rejection fails) | The concern is "replace reflection-based `ReflectingExecutor<T>` with compile-time source generator." Removal of the reflection path is within that domain. | YES — stays within domain |

**Grounding audit summary:** Q4 rejection succeeds — removing `ReflectingExecutor<T>` immediately would create a worse defect class (runtime `TypeLoadException` for unconverted consumers) compared to the current state (compile-time `[Obsolete]` warning). However, this is a **timing** concern, not a structural one. The source.md states "This type will be removed in v1.0" and "Clean break - requires direct Executor inheritance," explicitly approving future removal.

**Decision:**
- Candidate 0 (Phase 0): No candidate exists — the concern is not frame-artificial.
- Candidate 1: Passes subtraction gate. Survives 4 of 5 rejection questions. Q4 succeeds because immediate removal creates binary compatibility risk. This makes it a **Frame-lift offered** rather than **Frame-lift required**.
- Candidate 2: Fails subtraction gate. Not evaluated further.

## Verdict

**Frame correct** (with grounded constraint)

**Rationale:**

The current framing of the problem — a source generator that replaces a reflection-based pattern — is structurally sound. The concern (handler-to-route binding) cannot be eliminated by removing an abstraction; it is an inherent requirement of the executor architecture (every executor must bind message types to handlers).

The source generator already exists and is fully operational (`ExecutorRouteGenerator.cs:22-161`). The design-under-review is describing and validating work that has already been implemented (codebase-snapshot.md section 4: "Files listed as 'to create' — All files ALREADY EXIST").

One elevation candidate survives with partial rejection: complete removal of the `Reflection/` subsystem would eliminate an entire category of runtime decisions (runtime reflection handler scanning) and delete ~414+ lines with zero additions. However, Q4 rejection succeeds because immediate removal creates a worse defect class (binary incompatibility for NuGet consumers). The source.md explicitly acknowledges this with "This type will be removed in v1.0" and the `[Obsolete(error: false)]` grace period.

Because the only surviving candidate is blocked by a grounded binary-compatibility constraint that the design itself has already addressed (via `[Obsolete]` + documented removal timeline), the frame is **correct** — the current approach of deprecate-then-remove is the right architecture for a published library with external consumers.

**No redesign required.** The elevation candidate (full `Reflection/` removal) is explicitly planned for a future version and correctly deferred by the `[Obsolete]` migration pattern.
