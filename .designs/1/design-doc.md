# Design: Roslyn Source Generator for Workflow Executor Routes

## Executive Summary

This design evaluates the plan to replace the reflection-based `ReflectingExecutor<T>` pattern with a compile-time Roslyn source generator using `[MessageHandler]` attributes. The key finding is that **the implementation already exists and is functionally complete** — the source generator, all three attributes, diagnostics, and test suite are already in the codebase with deliberate naming and API evolutions from the original plan.

The architecture elevation analysis confirms the design frame is correct: handler-to-route binding is an inherent requirement, and the compile-time source generator is the right approach. The reflection path (`ReflectingExecutor<T>`) is already marked `[Obsolete]` with a transitional deprecation strategy appropriate for a published library with external consumers.

The six-sigma gap analysis identified 13 quality gaps, 3 high-impact, all feasible to address. The most significant gaps are: (1) duplicate handler input types produce runtime exceptions instead of compile-time diagnostics, (2) no behavioral equivalence integration tests between generated and reflected routes, and (3) `[MessageHandler]` on `Executor<TInput>` subclasses is silently ignored with only Info-level severity. This design proposes addressing these gaps as incremental improvements to the existing implementation.

## Constraints Respected

All proposals respect the constraints captured in source.md:

- **C-1**: Target Framework — Generator targets `netstandard2.0` (.csproj line 5). COMPLIANT.
- **C-2**: Roslyn Version — Plan specifies 4.8.0+; implementation uses 4.4.0. DEVIATION: deliberate for broader SDK compatibility (.csproj lines 45-49 comment explains rationale). `ForAttributeWithMetadataName` API is available in 4.4.0. Functionally compliant.
- **C-3**: Analyzer Packaging — `IsRoslynComponent=true` (.csproj:16), `EnforceExtendedAnalyzerRules=true` (.csproj:17), `PackagePath="analyzers/dotnet/cs"` (.csproj:55). COMPLIANT.
- **C-4**: Migration Strategy — Clean break via `[Obsolete]` on `ReflectingExecutor<T>` (ReflectingExecutor.cs:21-22) and `IMessageHandler<T>` (IMessageHandler.cs:17-18, 42-43). Direct `Executor` inheritance required for source generation. COMPLIANT.
- **C-5**: Handler Accessibility — `SemanticAnalyzer.AnalyzeHandler` (line 462) performs no accessibility check. Handlers of any access level are accepted. COMPLIANT.
- **C-6**: Partial Modifier — `SemanticAnalyzer.IsPartialClass` (lines 367-380) enforces the partial requirement; violation emits `MAFGENWF003` error. COMPLIANT.

## AC Traceability (REQUIRED)

| AC id | Verbatim quote from source.md | Clause breakdown | Addressed by | Status |
|-------|------------------------------|------------------|--------------|--------|
| AC-1 | "dotnet/src/Microsoft.Agents.AI.Workflows.Generators/ ├── ... ├── Analysis/ │ ├── SyntaxDetector.cs │ └── SemanticAnalyzer.cs ..." | (i) .csproj (ii) ExecutorRouteGenerator.cs (iii-iv) Models/ (v) SyntaxDetector.cs (vi-viii) Analysis, Generation, Diagnostics | Generator project | PARTIAL: SyntaxDetector.cs does not exist as separate file; detection is inline via `ForAttributeWithMetadataName`. All other files exist. |
| AC-2 | "Target netstandard2.0, Reference Microsoft.CodeAnalysis.CSharp 4.8.0+, IsRoslynComponent=true, EnforceExtendedAnalyzerRules=true, analyzers/dotnet/cs" | (i) TFM (ii) Roslyn version (iii-iv) MSBuild props (v) pack path | Generator .csproj | PARTIAL: Roslyn is 4.4.0 not 4.8.0 (deliberate deviation). All other clauses met. |
| AC-3 | "MessageHandlerAttribute with Yield and Send properties" | (i-vi) AttributeUsage, sealed, Yield, Send | MessageHandlerAttribute.cs:48-70 | MET |
| AC-4 | "SendsMessageAttribute with Type property" | (i-vi) AttributeUsage, sealed, Type, constructor | SendsMessageAttribute.cs:32-49 | MET (targets Class\|Method, broader than plan's Class-only) |
| AC-5 | "YieldsMessageAttribute with Type property" | (i-vii) AttributeUsage, sealed, Type, constructor, name | YieldsOutputAttribute.cs:32-49 | PARTIAL: named YieldsOutputAttribute, not YieldsMessageAttribute |
| AC-6 | "partial modifier, [MessageHandler] method detection" | (i) partial check (ii) attribute detection | SemanticAnalyzer.cs:367-380, ExecutorRouteGenerator.cs:33-37 | MET |
| AC-7 | "Executor derivation, ConfigureRoutes not defined, valid signature, valid return type" | (i) derivation (ii) override check (iii) signature (iv) return type | SemanticAnalyzer.cs:385-400, 406-418, 462-533, 539-569 | MET (checks ConfigureProtocol not ConfigureRoutes) |
| AC-8 | "Handler signature → AddHandler mapping" | (i-vi) 6 signature patterns | SourceBuilder.cs:178-189, HandlerSignatureKind enum | MET |
| AC-9 | "Generated ConfigureRoutes/ConfigureSentTypes/ConfigureYieldTypes" | (i-iii) three method overrides (iv-v) headers | SourceBuilder.cs:27-127 | DEVIATION: generates unified ConfigureProtocol with fluent API, not separate methods |
| AC-10 | "Inheritance: no base call vs base call" | (i-iii) three scenarios | ExecutorInfo.BaseHasConfigureProtocol, SourceBuilder.cs:79-84 | MET (uses ConfigureProtocol not ConfigureRoutes) |
| AC-11 | "WFGEN001-006 diagnostics" | (i-vi) 6 diagnostic rules | DiagnosticDescriptors.cs:34-107 | DEVIATION: uses MAFGENWF001-007 (7 diagnostics, includes static handler check MAFGENWF007) |
| AC-12 | "ProjectReference as Analyzer" | (i-iii) ProjectReference, OutputItemType, ReferenceOutputAssembly | Workflows .csproj:35-39 | MET |
| AC-13 | "ReflectingExecutor marked [Obsolete]" | (i-iii) [Obsolete], message, error:false | ReflectingExecutor.cs:21-22 | MET (message says "future version" not "v1.0") |
| AC-14 | "IMessageHandler marked [Obsolete]" | (i-ii) both interfaces | IMessageHandler.cs:17-18, 42-43 | MET |
| AC-15 | "Generator unit tests" | (i) ExecutorRouteGeneratorTests.cs (ii) SyntaxDetectorTests.cs (iii) SemanticAnalyzerTests.cs (iv) GeneratorTestHelper.cs (v-xiii) test scenarios | Tests project: 33 test methods in ExecutorRouteGeneratorTests.cs | PARTIAL: SyntaxDetectorTests.cs and SemanticAnalyzerTests.cs do not exist. Test coverage integrated in ExecutorRouteGeneratorTests.cs. |
| AC-16 | "Port ReflectingExecutor tests, verify behavioral equivalence" | (i) ported tests (ii) behavioral equivalence | ReflectionSmokeTest.cs exists but only tests reflection path | GAP: No behavioral equivalence test exists (Gap 7) |
| AC-17 | "12 files to create" | (i-xii) individual files | All exist except SyntaxDetector.cs (inline) and YieldsMessageAttribute.cs (named YieldsOutputAttribute.cs) | PARTIAL: 10/12 exist exactly, 2 have deliberate deviations |
| AC-18 | "4 files to modify" | (i-iv) .csproj, ReflectingExecutor, IMessageHandler, solution | All modifications present | MET (solution is .slnx not .sln) |
| AC-19 | "Example usage end state" | (i-iv) class-level attrs, return inference, explicit Yield/Send, generated output | Source generator pipeline | DEVIATION: generated code uses ConfigureProtocol pattern, not separate methods |

## Architecture Elevation Verdict

**Verdict**: Frame correct (with grounded constraint)

The design concern — replacing reflection with compile-time source generation — is structurally sound. The concern cannot be eliminated by removing any abstraction; handler-to-route binding is an inherent requirement of the executor architecture. Five concerning abstractions were evaluated (ReflectingExecutor, IMessageHandler interfaces, RouteBuilderExtensions, MessageHandlerInfo, ValueTaskTypeErasure); none, if removed alone, would eliminate the need for handler binding.

One elevation candidate (complete removal of the Reflection/ subsystem, ~487 lines across 6 files) survived the subtraction gate but was rejected by the self-challenge: immediate removal would create `TypeLoadException` failures for NuGet consumers not yet migrated. The current `[Obsolete]` deprecation approach is the correct architecture for a published library.

## Problem Statement

> Replace the reflection-based `ReflectingExecutor<T>` pattern with a compile-time source generator that discovers `[MessageHandler]` attributed methods and generates `ConfigureRoutes`, `ConfigureSentTypes`, and `ConfigureYieldTypes` implementations.

(Verbatim from source.md)

## Proposed Design

### Overview

The source generator is already implemented and functional. This design validates the implementation against the original plan, documents deliberate deviations, and proposes incremental improvements to close quality gaps identified by independent analysis. The design recommends preserving the current implementation with targeted enhancements.

### Key Components (All Existing)

1. **ExecutorRouteGenerator** (`ExecutorRouteGenerator.cs:22-161`) — IIncrementalGenerator with three attribute-driven pipelines
2. **SemanticAnalyzer** (`Analysis/SemanticAnalyzer.cs`) — Handler method validation and class analysis
3. **SourceBuilder** (`Generation/SourceBuilder.cs:27-127`) — ConfigureProtocol code emission with fluent API
4. **DiagnosticDescriptors** (`Diagnostics/DiagnosticDescriptors.cs:34-107`) — 7 diagnostic rules (MAFGENWF001-007)
5. **Data Models** (`Models/`) — ExecutorInfo, HandlerInfo, and 6 supporting record types
6. **Attributes** — MessageHandlerAttribute, SendsMessageAttribute, YieldsOutputAttribute

### Component Dependency Graph

```
Attribute Definitions (Workflows package)
    ↓ consumed by
ExecutorRouteGenerator (ForAttributeWithMetadataName pipelines)
    ↓ delegates to
SemanticAnalyzer (validation + data extraction)
    ↓ produces
ExecutorInfo + HandlerInfo (immutable data models)
    ↓ consumed by
SourceBuilder (code emission → ConfigureProtocol override)
    ↓ references
DiagnosticDescriptors (error/warning reporting)
```

Build order: Attributes → Generator .csproj (netstandard2.0) → Workflows .csproj (analyzer reference) → Tests

### Interface

The user-facing API consists of three attributes:

| Attribute | Target | Purpose |
|-----------|--------|---------|
| `[MessageHandler]` | Method | Marks a method as a handler; optional `Yield`/`Send` type arrays |
| `[SendsMessage(typeof(T))]` | Class, Method | Declares sent message types for protocol validation |
| `[YieldsOutput(typeof(T))]` | Class, Method | Declares yielded output types for protocol validation |

Seven diagnostics provide compile-time feedback:

| ID | Severity | Condition |
|----|----------|-----------|
| MAFGENWF001 | Error | Handler missing IWorkflowContext parameter |
| MAFGENWF002 | Error | Handler has invalid return type |
| MAFGENWF003 | Error | Executor with [MessageHandler] must be partial |
| MAFGENWF004 | Warning | [MessageHandler] on non-Executor class |
| MAFGENWF005 | Error | Handler has fewer than 2 parameters |
| MAFGENWF006 | Info | ConfigureProtocol already defined |
| MAFGENWF007 | Error | Handler cannot be static |

### Data Model

The generator pipeline uses immutable records with value equality for incremental caching:

- **ExecutorInfo** (`Models/ExecutorInfo.cs:18`) — Class metadata, handler list, class-level type declarations
- **HandlerInfo** (`Models/HandlerInfo.cs:34`) — Method name, input/output types, signature kind, explicit Yield/Send types
- **HandlerSignatureKind** — Enum: VoidSync, VoidAsync, ResultSync, ResultAsync

Supporting types: MethodAnalysisResult, ClassProtocolInfo, AnalysisResult, ProtocolAttributeKind, ImmutableEquatableArray<T>.

## Cross-Dimension Trade-offs

| Conflict | Resolution | Rationale |
|----------|------------|-----------|
| D1 (API) vs D6 (Integration): Plan naming differs from implementation (YieldsMessage→YieldsOutput, ConfigureRoutes→ConfigureProtocol, WFGEN→MAFGENWF) | Document mapping; accept deviation | Renaming would break existing consumers; aliases add complexity. Deviations are deliberate (commit 0756c457) |
| D2 (Data) vs D6 (Integration): Roslyn 4.8.0+ specified but 4.4.0 used | Keep 4.4.0; document deviation | 4.4.0 provides ForAttributeWithMetadataName; upgrading breaks .NET 7 SDK users. .csproj:45-48 documents rationale |

## Cross-Perspective Conflicts

| Finding Source | Finding | Conflicts With | Nature | Resolution |
|---------------|---------|----------------|--------|------------|
| Elevation | Frame correct; no lift needed | Dimensions (all recommend status quo) | No conflict — aligned | Both perspectives confirm current design is sound |
| Gap Analysis (Gap 4) | Duplicate handlers cause runtime crash — `RouteBuilder.AddHandler<T>` throws `ArgumentException` ("An item with the same key has already been added") when two handlers register the same input type, producing an unhandled exception during executor construction | Dimensions (API recommends current diagnostics) | Tension: API analysis did not flag this gap | Add MAFGENWF008 diagnostic for duplicate input types. Diagnostic message should reference the specific `ArgumentException` users would otherwise encounter at runtime |
| Gap Analysis (Gap 9) | Info-level for ConfigureProtocol override on Executor<T> subclasses | Dimensions (UX recommends current diagnostic levels) | Tension: Info severity masks user intent | Upgrade MAFGENWF006 to Warning when base is Executor<T>/Executor<T,TOut> |
| Gap Analysis (Gap 7) | No behavioral equivalence tests | Dimensions (Integration notes test coverage adequate) | Tension: structural tests insufficient for migration validation | Add curated equivalence verification test set |
| Decision History | commit 0756c457 (Config→ExecutorConfig, RouteBuilder explicit) | All dimensions respect this | No conflict | Dimensions correctly avoid reversing this change |

## Decisions Made

| Decision | Options Considered | Chosen | Rationale | Reversibility |
|----------|-------------------|--------|-----------|---------------|
| Preserve YieldsOutputAttribute name | (a) Rename to match plan (b) Keep actual name (c) Add alias | (b) Keep YieldsOutputAttribute | Aligns with `YieldsOutput<T>()` fluent API; renaming breaks consumers | Easy |
| Preserve ConfigureProtocol unified API | (a) Revert to separate methods (b) Keep unified ProtocolBuilder | (b) Keep unified | Cleaner API, matches Executor.cs:216 abstract; fewer override points | Moderate |
| Keep Roslyn 4.4.0 | (a) Upgrade to 4.8.0+ (b) Keep 4.4.0 | (b) Keep 4.4.0 | Broader SDK compatibility; all needed APIs available in 4.4.0 | Easy |
| Keep MAFGENWF diagnostic IDs | (a) Rename to WFGEN (b) Keep MAFGENWF | (b) Keep MAFGENWF | Follows Microsoft Agent Framework naming convention | Easy |
| Add duplicate handler diagnostic | (a) Leave as runtime error (b) Add compile-time check | (b) Add MAFGENWF008 | Catches error at build time; prevents runtime crash | Easy |
| Upgrade MAFGENWF006 for Executor<T> | (a) Keep Info (b) Upgrade to Warning | (b) Warning for Executor<T> base | Users clearly intend [MessageHandler] to work | Easy |

## Risk Registry

| Risk | Severity | Likelihood | Mitigation | Owner | Source |
|------|----------|-----------|------------|-------|--------|
| NuGet consumers on ReflectingExecutor lose functionality when deprecated type is removed | High | Medium | Transitional [Obsolete] warning → error → removal across major versions | API | Elevation |
| AutoYieldOutput=false breaks return-type yield registration | Medium | Low | Document runtime dependency in design doc and API docs | Integration | Gap 6 |
| Roslyn API behavior changes in future SDK versions | Medium | Low | Pin to 4.4.0 minimum; test against multiple SDK versions in CI | Integration | Gap 1 |
| Multi-file partial class edge cases in incremental caching | Low | Low | Add explicit multi-file test case (Gap 13) | Data | Gap 13 |
| Method-level [SendsMessage]/[YieldsOutput] on non-handler methods silently ignored | Low | Low | Document limitation in API docs | API | Gap 12 |
| New diagnostics (MAFGENWF008, upgraded MAFGENWF006) break consumer CI builds | Medium | Medium | Ship MAFGENWF008 as Warning (not Error) initially; document new diagnostics in release notes. Consumers with TreatWarningsAsErrors will see build breaks — mitigate by upgrading to Error only in the next major version | API | Cross-review H3 |

## Six-Sigma Caveats

| Gap | Category | Impact | Feasibility | Constraint |
|-----|----------|--------|-------------|------------|
| Gap 1 | version drift | Low | Feasible | Documentation correction only |
| Gap 2 | escape path | Medium | Feasible | New diagnostic for 4+ parameters |
| Gap 3 | escape path | Medium | Feasible | New diagnostic for non-CT third parameter |
| Gap 4 | escape path | High | Feasible | Duplicate input type detection in CombineHandlerMethodResults |
| Gap 5 | scope gap | Low | Feasible | Documentation naming clarification |
| Gap 6 | unstated assumption | Medium | Feasible | Document AutoYield runtime dependency |
| Gap 7 | test type mismatch | High | Partially feasible | Blocker: structural tests (source text comparison) cannot verify runtime behavioral equivalence. The test project has CSharpCompilation infrastructure for generator output verification, but proving generated routes match reflected routes requires runtime execution of generated code against actual `RouteBuilder`/`ProtocolBuilder` instances — this needs an integration test host that compiles, loads, and executes generated assemblies. Structural baseline comparisons (Phase 2 deliverable) are feasible; full runtime equivalence is not without additional test infrastructure |
| Gap 8 | sibling vulnerability | Low | Feasible | Document auto-send/yield delegation |
| Gap 9 | escape path | High | Feasible | Upgrade diagnostic severity for Executor<T> case |
| Gap 10 | version drift | Very Low | Feasible | Replace hint name approximation with precise count |
| Gap 11 | observability gap | Medium | Feasible | Create migration guide document |
| Gap 12 | escape path | Low | Feasible | Document method-level attribute scope |
| Gap 13 | test type mismatch | Medium | Feasible | Add multi-file partial class test |

**Practical ceiling**: The generator cannot validate runtime configuration (`ExecutorOptions`) at compile time. Exact behavioral parity between source-generated and reflected paths requires runtime integration tests. These are irreducible constraints of the compile-time/runtime boundary.

**Residual risks accepted**: Runtime option validation impossible at compile time; incremental caching edge cases with complex partial class topologies.

## Implementation Plan

### Phase 1: High-Impact Gap Closure (Effort: Small)

**Deliverables:**
1. New diagnostic `MAFGENWF008` for duplicate input type handlers on same executor (ship as Warning initially to avoid breaking consumer CI with TreatWarningsAsErrors; upgrade to Error in next major version)
2. Upgrade `MAFGENWF006` severity to Warning when base class is `Executor<TInput>` or `Executor<TInput, TOutput>`
3. New diagnostic for handler methods with 4+ parameters
4. New diagnostic for non-CancellationToken third parameter

**Source ACs satisfied**: AC-11 (enhanced diagnostics)
**Dependencies**: None — changes are additive to existing DiagnosticDescriptors.cs and SemanticAnalyzer.cs
**Risks addressed**: Gap 4 (duplicate handlers), Gap 9 (silent ignore), Gap 2 (4+ params), Gap 3 (non-CT third param)
**Six-Sigma gaps closed**: Gaps 2, 3, 4, 9

**Phase acceptance criteria:**
- [ ] `MAFGENWF008` fires when two [MessageHandler] methods on the same class have the same input type
- [ ] `MAFGENWF006` severity is Warning (not Info) when the defining base class is `Executor<TInput>` or `Executor<TInput, TOutput>`
- [ ] Handler with 4+ parameters produces a descriptive diagnostic instead of passing validation
- [ ] Handler with non-CancellationToken third parameter produces a warning diagnostic

### Phase 2: Test Coverage Improvements (Effort: Small)

**Deliverables:**
1. Multi-file partial class test (two source strings, handler split across files)
2. Curated behavioral equivalence test set comparing generator output against known-good baselines

**Source ACs satisfied**: AC-15 (test coverage), AC-16 (behavioral equivalence, partial)
**Dependencies**: Phase 1 (new diagnostics should be tested too)
**Risks addressed**: Gap 7 (behavioral equivalence, partial), Gap 13 (multi-file partial)
**Six-Sigma gaps closed**: Gaps 7 (partially), 13

**Phase acceptance criteria:**
- [ ] Test passes with handler split across two source files
- [ ] At least 3 baseline comparison tests verify generator output matches expected ConfigureProtocol pattern for common executor configurations

### Phase 3: Documentation and Migration Guide (Effort: Small)

**Deliverables:**
1. Migration guide document: steps to convert from `ReflectingExecutor<T>` to `[MessageHandler]` pattern
2. Document auto-yield/auto-send runtime dependency
3. Document plan-vs-implementation deviations (naming, API shape, diagnostic IDs)
4. Document method-level attribute scope limitations

**Source ACs satisfied**: AC-13 (migration guidance), AC-5 (naming clarification)
**Dependencies**: None
**Risks addressed**: Gap 5 (naming), Gap 6 (auto-yield), Gap 8 (auto-send delegation), Gap 11 (migration guide), Gap 12 (method-level attrs)
**Six-Sigma gaps closed**: Gaps 1, 5, 6, 8, 10, 11, 12

**Phase acceptance criteria:**
- [ ] Migration guide document exists with step-by-step conversion instructions
- [ ] Auto-yield/auto-send runtime dependency documented in API doc comments

## Appendix: Analysis Artifacts

- [source.md](source.md)
- [verification.md](verification.md)
- [codebase-snapshot.md](codebase-snapshot.md)
- Dimension analyses: [api.md](api.md), [data.md](data.md), [ux.md](ux.md), [scale.md](scale.md), [security.md](security.md), [integration.md](integration.md)
- [audit.md](audit.md)
- [conflicts.md](conflicts.md)
- [dependencies.md](dependencies.md)
- [elevation_assessment.md](elevation_assessment.md)
- [six_sigma_gaps.md](six_sigma_gaps.md)
- [verification-report.md](verification-report.md)
- [synthesis-checklist.md](synthesis-checklist.md)
