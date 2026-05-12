# Implementation Plan Outline: Roslyn Source Generator for Workflow Executor Routes

**Date**: 2026-05-12
**Source**: `.designs/1/design-doc.md`
**Purpose**: Self-contained phase extraction guide for creating focused
             IMPLREADME_PHASE{X}.md files
**Usage**: Extract any single phase section below and provide it to an LLM
           with: "Run `/design-plan-impl .designs/1/implementation-plan/implementation_plan_outline.md` to extract Phase X"

---

## How To Use This Document

Each phase below is a **self-contained extraction unit**. Workflow:

1. `/design-plan-impl .designs/1/design-doc.md` — produces this outline (Mode A)
2. `/clear`
3. `/peer-review .designs/1/implementation-plan/implementation_plan_outline.md` — validates outline against codebase
4. `/clear`
5. `/design-plan-impl .designs/1/implementation-plan/implementation_plan_outline.md` — extract Phase X into IMPLREADME (Mode B)
6. `/clear`
7. Use the phase's **Recommended Skill** to implement (e.g., `/ultra-implement`, `/terraform-fix`, or `/gherkin-design`)
8. Repeat steps 5-7 for each phase

**Phase dependency chain:**
```
Phase 1 (High-Impact Gap Closure)
    │
    ├──→ Phase 2 (Test Coverage)
    │
Phase 3 (Documentation) ← independent, can run in parallel with Phase 1
```

Phase 1 and Phase 3 have no dependency on each other and can run in parallel.
Phase 2 depends on Phase 1 because new diagnostics introduced in Phase 1 must be tested in Phase 2.

## Deployment Coverage

| Target | Scripts/Config | Covered By Phase | Gap? |
|--------|---------------|-----------------|------|
| CI Build (Ubuntu net10.0, Windows net9.0/net472, Ubuntu net8.0) | `.github/workflows/dotnet-build-and-test.yml` | All phases (auto-triggered on `dotnet/**` changes) | No |
| Unit Tests (net10.0 Ubuntu, net472 Windows) | `.github/workflows/dotnet-build-and-test.yml` `dotnet-test` job | Phase 1 (new diagnostic code), Phase 2 (new tests) | No |
| Code Coverage (80% threshold) | `dotnet/eng/scripts/dotnet-check-coverage.ps1` | Phase 2 | No |
| NuGet Packaging | `dotnet/nuget/nuget-package.props` (VersionPrefix: 1.5.0) | No code changes needed | No |
| Code Formatting | `.github/workflows/dotnet-format.yml` | All phases (auto-enforced) | No |
| Release/Publish | Manual process (no automated pipeline) | N/A — library code only | No |

## Success Metrics

| Metric | Source | Phase |
|--------|--------|-------|
| Duplicate input type handlers caught at compile time | design-doc.md Phase 1 AC, Gap 4 | Phase 1 |
| MAFGENWF006 upgraded to Warning for Executor<T> subclasses | design-doc.md Phase 1 AC, Gap 9 | Phase 1 |
| 4+ parameter handlers produce diagnostic | design-doc.md Phase 1 AC, Gap 2 | Phase 1 |
| Non-CancellationToken third parameter produces warning | design-doc.md Phase 1 AC, Gap 3 | Phase 1 |
| Multi-file partial class test passes | design-doc.md Phase 2 AC, Gap 13 | Phase 2 (already exists; verify) |
| 3+ baseline comparison tests verify ConfigureProtocol output | design-doc.md Phase 2 AC, Gap 7 | Phase 2 |
| Migration guide document exists | design-doc.md Phase 3 AC, Gap 11 | Phase 3 |
| Auto-yield/auto-send documented in API doc comments | design-doc.md Phase 3 AC, Gap 6 | Phase 3 |

---

## Phase 1: High-Impact Gap Closure — New Diagnostics

### Objective
Add four new compile-time diagnostics to the Roslyn source generator to catch handler configuration errors that currently surface only at runtime or are silently ignored.

### Prerequisites
None

### Recommended Skill
`/ultra-implement` — Pure C# library code changes to existing analyzer/generator infrastructure. No infrastructure, no UI, no design exploration needed.

### Design References
| Document | Section | Lines | What It Specifies |
|----------|---------|-------|-------------------|
| design-doc.md | Implementation Plan, Phase 1 | L188-199 | Deliverables: MAFGENWF008, upgraded MAFGENWF006, 4+ param diagnostic, non-CT third param diagnostic |
| design-doc.md | Phase 1 acceptance criteria | L202-205 | Four pass/fail acceptance criteria |
| design-doc.md | Cross-Perspective Conflicts | L137-138 | Gap 4 runtime crash: RouteBuilder.AddHandler throws ArgumentException for duplicate input types |
| design-doc.md | Cross-Perspective Conflicts | L139 | Gap 9: Info severity masks user intent on Executor<T> subclasses |
| design-doc.md | Risk Registry | L162 | Risk: new diagnostics break consumer CI builds (TreatWarningsAsErrors) |
| six_sigma_gaps.md | Gap 2 | Full section | 4+ parameter escape path |
| six_sigma_gaps.md | Gap 3 | Full section | Non-CancellationToken third parameter escape path |
| six_sigma_gaps.md | Gap 4 | Full section | Duplicate handler input types — runtime crash |
| six_sigma_gaps.md | Gap 9 | Full section | Info-level severity on Executor<T> subclasses |
| api.md | Diagnostics | Full section | Current diagnostic inventory and patterns |

### Current State (files to read for context)
| File | Lines | What's There |
|------|-------|-------------|
| `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Diagnostics/DiagnosticDescriptors.cs` | L34-106 | 7 existing diagnostics (MAFGENWF001-007). MAFGENWF006 at L89-95 is Info severity. MAFGENWF007 at L100-106 is the last defined diagnostic. |
| `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Analysis/SemanticAnalyzer.cs` | L462-533 | `AnalyzeHandler()` method: validates static (L470-473), param count >= 2 (L477-480), IWorkflowContext second param (L484-488), CancellationToken detection at position 3 (L492-493), return type (L496-501). No validation for 4+ params or non-CT third param. |
| `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Analysis/SemanticAnalyzer.cs` | L110-189 | `CombineHandlerMethodResults()`: groups methods by class key (L100), checks Executor derivation (L133-141), partial modifier (L143-150), manual ConfigureProtocol (L152-159). Collects valid handlers at L162-165. No duplicate input type detection. |
| `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Models/HandlerInfo.cs` | L34-47 | `HandlerInfo` record: stores `InputTypeName` as fully-qualified string (set at SemanticAnalyzer.cs L506 using `SymbolDisplayFormat.FullyQualifiedFormat`). No method location stored. |
| `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Models/ExecutorInfo.cs` | L18-27 | `ExecutorInfo` record: `Handlers` is `ImmutableEquatableArray<HandlerInfo>`. No base type classification stored. |
| `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/ExecutorRouteGenerator.cs` | L22-161 | Three pipelines: MessageHandler methods (L31-37), SendsMessage classes (L39-45), YieldsOutput classes (L47-53). CombineAllResults at L94-126. |
| `dotnet/src/Microsoft.Agents.AI.Workflows/Executor.cs` | L382-397 | `Executor<TInput>` — overrides `ConfigureProtocol`, implements `IMessageHandler<TInput>` |
| `dotnet/src/Microsoft.Agents.AI.Workflows/Executor.cs` | L407-423 | `Executor<TInput, TOutput>` — overrides `ConfigureProtocol`, implements `IMessageHandler<TInput, TOutput>` |
| `dotnet/Directory.Build.props` | Full file | `TreatWarningsAsErrors=true` — all new Warning-level diagnostics will break consumer builds |

### Required Changes

**File 1: `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Diagnostics/DiagnosticDescriptors.cs`**
- **After L106**: Add three new DiagnosticDescriptor fields:
  - `MAFGENWF008`: "Duplicate input type handler" — Severity: **Warning** (not Error, to avoid immediate CI breaks for consumers with TreatWarningsAsErrors). Message: "Class '{0}' has multiple [MessageHandler] methods for input type '{1}'. Only one handler per input type is allowed; at runtime, RouteBuilder.AddHandler throws ArgumentException for duplicates."
  - `MAFGENWF009`: "Handler has too many parameters" — Severity: **Error**. Message: "Method '{0}' marked with [MessageHandler] has {1} parameters; maximum 3 allowed (message, IWorkflowContext, optional CancellationToken)"
  - `MAFGENWF010`: "Handler third parameter must be CancellationToken" — Severity: **Warning**. Message: "Method '{0}' has third parameter of type '{1}'; expected CancellationToken or omit the third parameter"
- **L89-95**: Add a second DiagnosticDescriptor for MAFGENWF006 with Warning severity (e.g., `ConfigureProtocolAlreadyDefinedWarning`), or parameterize severity. The existing Info-level descriptor remains for non-Executor<T> base classes.

**File 2: `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Analysis/SemanticAnalyzer.cs`**
- **After L480 (param count check)**: Add validation for `Parameters.Length > 3` — report MAFGENWF009 and return null.
- **After L493 (CancellationToken detection)**: Add validation: if `Parameters.Length >= 3` and third param is NOT CancellationToken, report MAFGENWF010. Do NOT return null (this is a warning; the handler can still be used with 2 effective params).
- **After L165 (handler collection in CombineHandlerMethodResults)**: Add duplicate input type detection. Group collected handlers by `InputTypeName`; for each group with count > 1, emit MAFGENWF008 diagnostic. Requires tracking method locations — either extend `HandlerInfo` with a location field, or use a parallel data structure in `MethodAnalysisResult`.
- **L152-159 (MAFGENWF006 reporting)**: Add base type detection. Check if the class's base type's `OriginalDefinition` matches `Executor<T>` or `Executor<T,U>` (can check `OriginalDefinition.ToDisplayString()` or generic arity). If so, use Warning-severity descriptor; otherwise keep Info.

**File 3: `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Models/HandlerInfo.cs`** (possibly)
- **L34-47**: May need to add a `MethodLocation` field (e.g., `DiagnosticLocationInfo`) to `HandlerInfo` so that duplicate diagnostics can reference the specific method. Alternatively, track locations separately in `CombineHandlerMethodResults` via the `MethodAnalysisResult` input.

### Acceptance Criteria
```bash
# 1. MAFGENWF008 fires for duplicate input types
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ --filter "DuplicateInputType" --no-build 2>&1 | grep -c "PASS"
# Expected: >= 1

# 2. MAFGENWF006 severity is Warning for Executor<TInput> base
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ --filter "ConfigureProtocolWarning" --no-build 2>&1 | grep -c "PASS"
# Expected: >= 1

# 3. Handler with 4+ parameters produces MAFGENWF009
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ --filter "TooManyParameters" --no-build 2>&1 | grep -c "PASS"
# Expected: >= 1

# 4. Non-CancellationToken third parameter produces MAFGENWF010
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ --filter "NonCancellationTokenThirdParam" --no-build 2>&1 | grep -c "PASS"
# Expected: >= 1

# 5. All existing tests still pass (no regressions)
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ 2>&1 | tail -5
# Expected: "Passed!" with 0 failures

# 6. Solution builds without errors
cd dotnet && dotnet build src/Microsoft.Agents.AI.Workflows.Generators/ 2>&1 | grep -c "Build succeeded"
# Expected: 1
```

### Gotchas (from codebase investigation)
- `TreatWarningsAsErrors=true` in `dotnet/Directory.Build.props` means any new Warning-level diagnostic (MAFGENWF008, MAFGENWF010, upgraded MAFGENWF006) will immediately fail builds for consumers. The design-doc risk registry addresses this: ship as Warning initially, upgrade to Error in the next major version. This is already the plan.
- `HandlerInfo` is an immutable record used for incremental caching (Roslyn IIncrementalGenerator pipeline). Adding a `DiagnosticLocationInfo` field to it will change its value equality semantics. Evaluate whether this causes unnecessary re-generation. The `ImmutableEquatableArray<T>` wrapper uses structural equality. Consider whether location info should be excluded from equality comparison.
- `CombineHandlerMethodResults()` receives `ImmutableArray<MethodAnalysisResult>` grouped by class key. `MethodAnalysisResult` already contains location info via the syntax node. Use this existing location data for duplicate diagnostics rather than modifying `HandlerInfo`.
- The MAFGENWF006 severity upgrade requires knowing the base type at the `CombineHandlerMethodResults` level. The `MethodAnalysisResult` contains `HasManualConfigureProtocol` but not the base type classification. You'll need to add a `BaseIsGenericExecutor` boolean (or similar) to `MethodAnalysisResult` during `AnalyzeHandlerMethod`, by checking if the class's base type's `OriginalDefinition` is `Executor<T>` or `Executor<T,U>`. The `DerivesFromExecutor()` method (lines 385-400) already walks the base type chain — extend it.
- The existing CancellationToken detection at L492-493 checks `Parameters.Length >= 3` then checks the type. The new 4+ parameter check (MAFGENWF009) should run BEFORE the CancellationToken check. Order: (1) check < 2 params → MAFGENWF005, (2) check > 3 params → MAFGENWF009, (3) check IWorkflowContext at position 1, (4) check CancellationToken at position 2 and non-CT third param → MAFGENWF010.
- The non-CT third parameter diagnostic (MAFGENWF010) should NOT prevent handler registration. The handler is still valid with its first two parameters. Only emit the warning and continue processing.

---

## Phase 2: Test Coverage Improvements

### Objective
Add baseline comparison tests that verify the source generator produces the expected ConfigureProtocol code patterns for common executor configurations, closing the behavioral equivalence gap.

### Prerequisites
Phase 1 (new diagnostics should be testable)

### Recommended Skill
`/ultra-implement` — C# test code following established xUnit.v3 + FluentAssertions patterns. No infrastructure or design exploration needed.

### Design References
| Document | Section | Lines | What It Specifies |
|----------|---------|-------|-------------------|
| design-doc.md | Implementation Plan, Phase 2 | L208-216 | Deliverables: multi-file partial test, behavioral equivalence tests |
| design-doc.md | Phase 2 acceptance criteria | L218-220 | Multi-file test passes; 3+ baseline comparison tests |
| design-doc.md | Six-Sigma Caveats | L174 | Gap 7: structural tests insufficient for migration validation. Practical ceiling: full runtime equivalence needs test infrastructure beyond current capabilities. |
| design-doc.md | Six-Sigma Caveats | L180 | Gap 13: multi-file partial class test |
| six_sigma_gaps.md | Gap 7 | Full section | Test type mismatch — no behavioral equivalence tests |
| six_sigma_gaps.md | Gap 13 | Full section | Multi-file partial class edge case |

### Current State (files to read for context)
| File | Lines | What's There |
|------|-------|-------------|
| `dotnet/tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ExecutorRouteGeneratorTests.cs` | L541-704 | **Multi-file partial class tests already exist**: `PartialClass_SplitAcrossFiles_GeneratesCorrectly()` (L543-604), `PartialClass_HandlersInBothFiles_GeneratesAllHandlers()` (L606-651), `PartialClass_SendsYieldsInBothFiles_GeneratesAllOverrides()` (L653-704). These satisfy the multi-file test requirement. |
| `dotnet/tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ExecutorRouteGeneratorTests.cs` | L14-135 | Single handler test patterns (void, ValueTask, ValueTask<T>, with CancellationToken). These demonstrate the baseline comparison approach: call `RunGenerator()`, assert generated tree contains expected patterns. |
| `dotnet/tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/GeneratorTestHelper.cs` | L20-145 | Test helper API: `RunGenerator(params string[] sources)` (L31-54), `AssertGeneratesSource()` (L59-67), `AssertProducesDiagnostic()` (L81-88). Returns `GeneratorRunResult` record with `RunResult`, `OutputCompilation`, `Diagnostics`. |
| `dotnet/tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/SyntaxTreeFluentExtensions.cs` | Full file | Fluent assertion methods: `AddHandler()` (L20-72), `RegisterSentMessageType()` (L85-103), `RegisterYieldedOutputType()` (L116-134), `HaveHierarchy()` (L169-192). |
| `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Generation/SourceBuilder.cs` | L71-110 | Generated ConfigureProtocol pattern: `protocolBuilder.SendsMessage<T>().YieldsOutput<T>().ConfigureRoutes(ConfigureRoutes)` with nested `void ConfigureRoutes(RouteBuilder routeBuilder)` local function. Base call when `BaseHasConfigureProtocol` is true. |
| `dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests/ReflectionSmokeTest.cs` | L69-128 | Reflection-based test using `ReflectingExecutor<T>` and `IMessageHandler<T>`. Uses `MessageRouter` and `.RouteMessageAsync()`. Demonstrates the old pattern for comparison. |
| `dotnet/tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/Microsoft.Agents.AI.Workflows.Generators.UnitTests.csproj` | Full file | Test framework: net10.0, xUnit.v3, FluentAssertions, Microsoft.CodeAnalysis.CSharp. References both Generators and Workflows projects. |

### Required Changes

**File 1: `dotnet/tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ExecutorRouteGeneratorTests.cs`**
- **After existing test sections (~end of file)**: Add a new test region/section for baseline comparison tests. Add at least 3 tests:

  1. **Simple single-handler baseline**: Define an executor with one `void Handler(string, IWorkflowContext)` method. Assert generated output contains exact expected ConfigureProtocol body with `routeBuilder.AddHandler<global::System.String>(this.Handler)`.

  2. **Multi-handler with mixed signatures baseline**: Define an executor with a void handler and a `ValueTask<int>` handler. Assert generated output contains both `.AddHandler<TIn>(this.Method1)` and `.AddHandler<TIn, global::System.Int32>(this.Method2)` registrations.

  3. **Full protocol baseline (handlers + class-level SendsMessage + YieldsOutput)**: Define an executor with `[SendsMessage(typeof(Foo))]`, `[YieldsOutput(typeof(Bar))]`, and a handler. Assert generated output contains `.SendsMessage<...>()`, `.YieldsOutput<...>()`, and `.ConfigureRoutes(ConfigureRoutes)` with the handler registration.

- **Additionally**: Add tests for Phase 1's new diagnostics (MAFGENWF008, MAFGENWF009, MAFGENWF010, upgraded MAFGENWF006) following the existing diagnostic test pattern (L708-832). Each diagnostic test: create source code that triggers the condition, call `GeneratorTestHelper.AssertProducesDiagnostic(source, "MAFGENWF00X")`.

### Acceptance Criteria
```bash
# 1. Multi-file partial class test passes (already exists)
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ --filter "PartialClass_SplitAcrossFiles" 2>&1 | grep -c "Passed"
# Expected: 1

# 2. At least 3 baseline comparison tests exist and pass
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ --filter "Baseline" 2>&1 | grep "Passed"
# Expected: >= 3 test names containing "Baseline" shown as passed

# 3. New diagnostic tests pass
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ --filter "DuplicateInputType|TooManyParameters|NonCancellationToken|ConfigureProtocolWarning" 2>&1 | grep "Passed"
# Expected: >= 4 tests passed

# 4. Full test suite still passes
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ 2>&1 | tail -5
# Expected: "Passed!" with 0 failures

# 5. Baseline tests verify full generated output (not just substring)
grep -c "GetText()" dotnet/tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ExecutorRouteGeneratorTests.cs
# Expected: >= 3 (baseline tests read full generated text)
```

### Gotchas (from codebase investigation)
- Multi-file partial class tests already exist at lines 541-704. The design-doc Phase 2 AC says "Test passes with handler split across two source files" — this is already satisfied. The new work is the baseline comparison tests.
- `GeneratorTestHelper.RunGenerator()` returns `GeneratorRunResult` with `RunResult.GeneratedTrees`. Access generated source via `GeneratedTrees[0].GetText().ToString()`. Existing tests use `SyntaxTreeFluentExtensions` for targeted assertions; baseline tests should use `GetText()` for full-text comparison to verify exact output structure.
- The generated output format is: `// <auto-generated/>` header, `#nullable enable`, namespace, partial class, `ConfigureProtocol` override. See `SourceBuilder.cs:27-127` for the exact template. Baseline expected strings must match this format exactly, including whitespace.
- Tests run on net10.0 only. The generator targets netstandard2.0 but tests compile with net10.0 Roslyn. No cross-TFM test coverage for the generator itself.
- `SyntaxTreeFluentExtensions` assertions use `Contains()` on the generated text. Baseline tests should do full-text equality (trimmed) to catch regressions in formatting, ordering, or missing elements.
- The test project references the Workflows assembly directly (`typeof(Executor).Assembly` is loaded in GeneratorTestHelper.cs), so test source strings can reference actual types from the Workflows package.

---

## Phase 3: Documentation and Migration Guide

### Objective
Create a migration guide for users transitioning from `ReflectingExecutor<T>` to the `[MessageHandler]` attribute pattern, and document runtime dependencies and plan-vs-implementation deviations.

### Prerequisites
None (independent of Phase 1 and Phase 2)

### Recommended Skill
`manual` — Documentation-only deliverables: markdown file creation and XML doc comment additions. No code logic changes.

### Design References
| Document | Section | Lines | What It Specifies |
|----------|---------|-------|-------------------|
| design-doc.md | Implementation Plan, Phase 3 | L222-233 | Deliverables: migration guide, auto-yield/send docs, deviation docs, method-level scope docs |
| design-doc.md | Phase 3 acceptance criteria | L235-237 | Migration guide exists; auto-yield/send documented |
| design-doc.md | Decisions Made | L144-149 | Deliberate deviations: YieldsOutput name, ConfigureProtocol API, Roslyn 4.4.0, MAFGENWF IDs |
| design-doc.md | Cross-Dimension Trade-offs | L128-131 | Naming and Roslyn version trade-offs |
| design-doc.md | Risk Registry | L158 | AutoYieldOutput=false breaks return-type yield registration |
| design-doc.md | Six-Sigma Caveats | L171 | Gap 6: auto-yield runtime dependency |
| design-doc.md | Six-Sigma Caveats | L179 | Gap 12: method-level attribute scope |
| six_sigma_gaps.md | Gap 1 | Full section | Version drift documentation |
| six_sigma_gaps.md | Gap 5 | Full section | Naming clarification |
| six_sigma_gaps.md | Gap 6 | Full section | Auto-yield unstated assumption |
| six_sigma_gaps.md | Gap 8 | Full section | Sibling vulnerability — auto-send delegation |
| six_sigma_gaps.md | Gap 11 | Full section | Observability gap — no migration guide |
| six_sigma_gaps.md | Gap 12 | Full section | Method-level attribute scope |

### Current State (files to read for context)
| File | Lines | What's There |
|------|-------|-------------|
| `dotnet/src/Microsoft.Agents.AI.Workflows/Reflection/ReflectingExecutor.cs` | Full file (77 lines) | `ReflectingExecutor<TExecutor>` — already marked `[Obsolete]` (L21-22). Uses reflection via `typeof(TExecutor).GetHandlerInfos()` (L43) to discover handlers. Overrides `ConfigureProtocol(ProtocolBuilder)`. Shows the pattern users must migrate away from. |
| `dotnet/src/Microsoft.Agents.AI.Workflows/Reflection/IMessageHandler.cs` | Full file (56 lines) | `IMessageHandler<TMessage>` (L19-30) and `IMessageHandler<TMessage, TResult>` (L44-55) — both `[Obsolete]` (L17-18, L42-43). Signatures: `ValueTask HandleAsync(TMessage, IWorkflowContext, CancellationToken)` and `ValueTask<TResult> HandleAsync(...)`. |
| `dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/MessageHandlerAttribute.cs` | Full file (71 lines) | Has XML doc comments (L7-28) with example usage (L30-46). Documents `Yield` (L51-59) and `Send` (L61-69) properties. |
| `dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/SendsMessageAttribute.cs` | Full file (50 lines) | Has XML doc comments (L8-20) with example (L23-30). `AttributeTargets.Class | Method`. |
| `dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/YieldsOutputAttribute.cs` | Full file (50 lines) | Has XML doc comments (L8-20) with example (L23-30). Named `YieldsOutputAttribute` not `YieldsMessageAttribute` per plan. |
| `dotnet/src/Microsoft.Agents.AI.Workflows/ExecutorOptions.cs` | Full file (27 lines) | `AutoSendMessageHandlerResultObject` (L20, default true), `AutoYieldOutputHandlerResultObject` (L25, default true). Minimal doc comments — needs expansion. |
| `dotnet/src/Microsoft.Agents.AI.Workflows/ProtocolBuilder.cs` | L156-172 | `Build(ExecutorOptions)` method: if `AutoSendMessageHandlerResultObject`, unions `router.DefaultOutputTypes` into send types (L161-163). If `AutoYieldOutputHandlerResultObject`, unions into yield types (L167-169). This is the auto-yield/send runtime logic. |
| `dotnet/src/Microsoft.Agents.AI.Workflows/Executor.cs` | L382-423 | `Executor<TInput>` and `Executor<TInput, TOutput>` — specialized base classes. `ChatProtocolExecutor` (separate file) disables `AutoSendMessageHandlerResultObject`. |
| `dotnet/src/Shared/Workflows/Execution/README.md` | Full file (12 lines) | Minimal existing doc — just a header. |
| No file | N/A | No MIGRATION.md, CHANGELOG.md, or migration guide exists anywhere in the Workflows package. |

### Required Changes

**File 1 (NEW): `dotnet/src/Microsoft.Agents.AI.Workflows/MIGRATION.md`**
Create a migration guide covering:
1. **Overview**: Why migrate (reflection overhead, compile-time safety, better diagnostics)
2. **Step-by-step conversion**:
   - Change base class from `ReflectingExecutor<TActual>` to `Executor` (or `Executor<TInput>` / `Executor<TInput, TOutput>`)
   - Add `partial` modifier to class declaration
   - Remove `IMessageHandler<T>` interface implementations
   - Add `[MessageHandler]` attribute to handler methods
   - Preserve `[SendsMessage]` and `[YieldsOutput]` class-level attributes (no change needed)
   - Remove manual `ConfigureProtocol` override (generated code handles it)
3. **Before/after code example**: Show a complete `ReflectingExecutor` converted to `[MessageHandler]`
4. **Auto-yield/auto-send behavior**: Explain `ExecutorOptions.AutoYieldOutputHandlerResultObject` and `AutoSendMessageHandlerResultObject` defaults (both true). Explain that when these are true, handler return values are automatically registered as yield/send types. Explain how to opt out.
5. **Naming differences from original plan**: YieldsOutputAttribute (not YieldsMessageAttribute), ConfigureProtocol (not ConfigureRoutes), MAFGENWF IDs (not WFGEN)
6. **Known limitations**: Method-level `[SendsMessage]`/`[YieldsOutput]` on non-handler methods are silently ignored. Partial class is required.

**File 2: `dotnet/src/Microsoft.Agents.AI.Workflows/ExecutorOptions.cs`**
- **L18-25**: Expand XML doc comments for `AutoSendMessageHandlerResultObject` and `AutoYieldOutputHandlerResultObject`. Add remarks explaining:
  - Default behavior (true): handler return types auto-registered
  - Runtime dependency: `ProtocolBuilder.Build()` unions `router.DefaultOutputTypes` when true
  - Impact on migration: users relying on explicit type registration may get unexpected auto-registration
  - Cross-reference to ProtocolBuilder.Build() for implementation details

**File 3: `dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/YieldsOutputAttribute.cs`**
- **L8-20**: Add a `<remarks>` section noting that this attribute was named `YieldsOutputAttribute` (not `YieldsMessageAttribute` as in the original design plan) to align with the `YieldsOutput<T>()` fluent API in `ProtocolBuilder`.

**File 4: `dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/SendsMessageAttribute.cs`**
- **L8-20**: Add a `<remarks>` section noting that method-level usage on non-`[MessageHandler]` methods has no effect. Only class-level declarations and method-level on `[MessageHandler]` methods participate in protocol registration.

**File 5: `dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/MessageHandlerAttribute.cs`**
- **L7-28**: Add a `<remarks>` section documenting the runtime dependency on `ExecutorOptions.AutoYieldOutputHandlerResultObject` and `AutoSendMessageHandlerResultObject`. When these are true (default), handler return types are automatically added to yield/send type sets beyond any explicit `Yield`/`Send` property values.

### Acceptance Criteria
```bash
# 1. Migration guide exists
test -f dotnet/src/Microsoft.Agents.AI.Workflows/MIGRATION.md && echo "EXISTS" || echo "MISSING"
# Expected: EXISTS

# 2. Migration guide contains step-by-step instructions
grep -c "Step" dotnet/src/Microsoft.Agents.AI.Workflows/MIGRATION.md
# Expected: >= 4 (at least 4 numbered steps)

# 3. Migration guide contains before/after example
grep -c "ReflectingExecutor" dotnet/src/Microsoft.Agents.AI.Workflows/MIGRATION.md
# Expected: >= 1

# 4. Auto-yield documented in ExecutorOptions
grep -c "AutoYield" dotnet/src/Microsoft.Agents.AI.Workflows/ExecutorOptions.cs
# Expected: >= 3 (property + expanded doc comments)

# 5. Auto-send documented in ExecutorOptions
grep -c "AutoSend" dotnet/src/Microsoft.Agents.AI.Workflows/ExecutorOptions.cs
# Expected: >= 3

# 6. YieldsOutputAttribute has naming clarification
grep -c "YieldsMessageAttribute\|original.*plan\|fluent API" dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/YieldsOutputAttribute.cs
# Expected: >= 1

# 7. Method-level scope documented
grep -c "non-handler\|silently ignored\|no effect" dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/SendsMessageAttribute.cs
# Expected: >= 1
```

### Gotchas (from codebase investigation)
- `ChatProtocolExecutor` (separate file) sets `AutoSendMessageHandlerResultObject = false`. The migration guide should mention that specialized executors may override these defaults, and users should check their base class.
- `RequestInfoExecutor` also sets `AutoSendMessageHandlerResultObject = false`. Document that not all executor bases have the same auto-send/yield defaults.
- The existing XML doc comments in attributes are well-written with examples (L30-46 in MessageHandlerAttribute.cs). New `<remarks>` additions should follow the same style.
- The `ReflectingExecutor<T>` obsolete message (L21-22) says "This type will be removed in a future version" — the migration guide should reference this timeline.
- There are no existing MIGRATION.md files in the repo for reference. The documentation style in the repo is minimal (12-line READMEs). The migration guide should be thorough but concise.
- Plan-vs-implementation deviations are already documented in the design-doc (lines 126-131, 144-149). The migration guide should reference these but frame them from a user perspective ("you may see `YieldsOutputAttribute` instead of `YieldsMessageAttribute`") rather than an internal design perspective.

---
