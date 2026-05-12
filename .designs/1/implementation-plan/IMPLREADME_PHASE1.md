# IMPLREADME Phase 1: High-Impact Gap Closure — New Diagnostics

**Source**: `.designs/1/implementation-plan/implementation_plan_outline.md`
**Phase**: 1 of 3
**Recommended Skill**: `/ultra-implement`

## Objective

Add four new compile-time diagnostics to the Roslyn source generator to catch handler configuration errors that currently surface only at runtime or are silently ignored.

## Prerequisites

None

## Design References

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

## Current State (files to read for context)

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

## Required Changes

**File 1: `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Diagnostics/DiagnosticDescriptors.cs`**
- **After L106**: Add three new DiagnosticDescriptor fields:
  - `MAFGENWF008`: "Duplicate input type handler" — Severity: **Warning** (not Error, to avoid immediate CI breaks for consumers with TreatWarningsAsErrors). Message: "Class '{0}' has multiple [MessageHandler] methods for input type '{1}'. Only one handler per input type is allowed; at runtime, RouteBuilder.AddHandler throws ArgumentException for duplicates."
  - `MAFGENWF009`: "Handler has too many parameters" — Severity: **Error**. Message: "Method '{0}' marked with [MessageHandler] has {1} parameters; maximum 3 allowed (message, IWorkflowContext, optional CancellationToken)"
  - `MAFGENWF010`: "Handler third parameter must be CancellationToken" — Severity: **Warning**. Message: "Method '{0}' has third parameter of type '{1}'; expected CancellationToken or omit the third parameter"
- **L89-95**: Add a second DiagnosticDescriptor for MAFGENWF006 with Warning severity (e.g., `ConfigureProtocolAlreadyDefinedWarning`), or parameterize severity. The existing Info-level descriptor remains for non-Executor<T> base classes.

**File 2: `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Analysis/SemanticAnalyzer.cs`**
- **After L480 (param count check)**: Add validation for `Parameters.Length > 3` — report MAFGENWF009 and return null.
- **After L493 (CancellationToken detection)**: Add validation: if `Parameters.Length >= 3` and third param is NOT CancellationToken, report MAFGENWF010. Do NOT return null (this is a warning; the handler can still be used with 2 effective params).
- **After L165 (handler collection in CombineHandlerMethodResults)**: Add duplicate input type detection. Group collected handlers by `InputTypeName`; for each group with count > 1, emit MAFGENWF008 diagnostic. Use method locations from `MethodAnalysisResult` (already available in the input `ImmutableArray<MethodAnalysisResult>`). **DO NOT modify `HandlerInfo`** — it is an immutable record used for incremental caching; adding location fields would change its value equality semantics and cause unnecessary re-generation.
- **L152-159 (MAFGENWF006 reporting)**: Add base type detection. Check if the class's base type's `OriginalDefinition` matches `Executor<T>` or `Executor<T,U>` (can check `OriginalDefinition.ToDisplayString()` or generic arity). If so, use Warning-severity descriptor; otherwise keep Info.

**Validation order in `AnalyzeHandler()` (IMPORTANT — must follow this sequence):**
1. Static check → MAFGENWF007 (existing, L470-473)
2. `Parameters.Length < 2` → MAFGENWF005 (existing, L477-480)
3. `Parameters.Length > 3` → MAFGENWF009 (**new**, insert after L480)
4. IWorkflowContext at position 1 → MAFGENWF001 (existing, L484-488)
5. CancellationToken detection at position 2 (existing, L492-493)
6. Non-CancellationToken third param → MAFGENWF010 (**new**, insert after L493)

## Acceptance Criteria

```bash
# 1. MAFGENWF008 fires for duplicate input types
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ --filter "DuplicateInputType" 2>&1 | grep -c "PASS"
# Expected: >= 1

# 2. MAFGENWF006 severity is Warning for Executor<TInput> base
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ --filter "ConfigureProtocolWarning" 2>&1 | grep -c "PASS"
# Expected: >= 1

# 3. Handler with 4+ parameters produces MAFGENWF009
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ --filter "TooManyParameters" 2>&1 | grep -c "PASS"
# Expected: >= 1

# 4. Non-CancellationToken third parameter produces MAFGENWF010
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ --filter "NonCancellationTokenThirdParam" 2>&1 | grep -c "PASS"
# Expected: >= 1

# 5. All existing tests still pass (no regressions)
cd dotnet && dotnet test tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/ 2>&1 | tail -5
# Expected: "Passed!" with 0 failures

# 6. Solution builds without errors
cd dotnet && dotnet build src/Microsoft.Agents.AI.Workflows.Generators/ 2>&1 | grep -c "Build succeeded"
# Expected: 1
```

## Gotchas (from codebase investigation)

- `TreatWarningsAsErrors=true` in `dotnet/Directory.Build.props` means any new Warning-level diagnostic (MAFGENWF008, MAFGENWF010, upgraded MAFGENWF006) will immediately fail builds for consumers. The design-doc risk registry addresses this: ship as Warning initially, upgrade to Error in the next major version. **Rollback strategy**: if MAFGENWF008/010 cause excessive consumer CI failures, they can be downgraded to Info severity in a patch release with a one-line change per diagnostic descriptor in DiagnosticDescriptors.cs — no behavioral change, only severity reduction.
- `HandlerInfo` is an immutable record used for incremental caching (Roslyn IIncrementalGenerator pipeline). DO NOT add location fields to it — this would change its value equality semantics and cause unnecessary re-generation. Instead, use method locations from `MethodAnalysisResult` (already available in `CombineHandlerMethodResults` input) for duplicate diagnostics.
- The MAFGENWF006 severity upgrade requires knowing the base type at the `CombineHandlerMethodResults` level. The `MethodAnalysisResult` contains `HasManualConfigureProtocol` but not the base type classification. You'll need to add a `BaseIsGenericExecutor` boolean (or similar) to `MethodAnalysisResult` during `AnalyzeHandlerMethod`, by checking if the class's base type's `OriginalDefinition` is `Executor<T>` or `Executor<T,U>`. The `DerivesFromExecutor()` method (lines 385-400) already walks the base type chain — extend it.
- The existing CancellationToken detection at L492-493 checks `Parameters.Length >= 3` then checks the type. The new 4+ parameter check (MAFGENWF009) should run BEFORE the CancellationToken check. Order: (1) check < 2 params → MAFGENWF005, (2) check > 3 params → MAFGENWF009, (3) check IWorkflowContext at position 1, (4) check CancellationToken at position 2 and non-CT third param → MAFGENWF010.
- The non-CT third parameter diagnostic (MAFGENWF010) should NOT prevent handler registration. The handler is still valid with its first two parameters. Only emit the warning and continue processing.

## Line Number Note

Line numbers are from a codebase snapshot taken at 2026-05-12. Locate by described code pattern if lines have shifted.

## Duplicate Detection Scope Note

Duplicate input type detection (MAFGENWF008) must run AFTER `CombineHandlerMethodResults` merges handlers from all partial class files, not within individual `AnalyzeHandler` calls. This ensures duplicates across partial class files are caught.
