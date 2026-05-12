# Six-Sigma Gap Analysis

**Date**: 2026-05-12
**Source**: source.md

## Gap Discovery Method
Independent analysis of escape paths, test type mismatches, sibling vulnerabilities,
version/config drift risks, and unstated assumptions. All codebase claims verified via
Read tool against the actual files in the worktree.

## Gaps Identified

### Gap 1: Roslyn Version Constraint Drift (Plan Says 4.8.0+, Actual Uses 4.4.0)

**Category**: version drift
**Current state**: The plan (AC-2, C-2) specifies `Microsoft.CodeAnalysis.CSharp` 4.8.0+, but the actual `.csproj` file at `dotnet/src/Microsoft.Agents.AI.Workflows.Generators/Microsoft.Agents.AI.Workflows.Generators.csproj` line 49 uses `VersionOverride="4.4.0"`. A code comment explains this is deliberate: "Use Roslyn 4.4.0 - minimum version for ForAttributeWithMetadataName API. Corresponds to .NET 7 SDK / VS 2022 17.4+. Higher versions would require newer SDKs, breaking users on older versions."
**Ideal state**: The plan should be corrected to reflect the actual constraint (4.4.0), or the design document should explicitly note the deviation and its rationale. If the plan were followed literally, it would break users on .NET 7 SDK / VS 2022 17.4-17.7.
**Feasibility**: Feasible
**Feasibility rationale**: This is a documentation correction. The actual implementation chose the right version for broader compatibility. The design document should document this as a deliberate deviation from the plan.

### Gap 2: Handler Methods With 4+ Parameters Silently Accepted

**Category**: escape path
**Current state**: The `SemanticAnalyzer.AnalyzeHandler` method (line 477) validates that `Parameters.Length >= 2` and checks whether parameter [1] is `IWorkflowContext` and parameter [2] (if present) is `CancellationToken`. However, it does NOT validate that there are no more than 3 parameters. A handler declared as `void Handle(string msg, IWorkflowContext ctx, CancellationToken ct, int extraParam)` would pass validation; the generator would treat `hasCancellationToken = true` and generate an `AddHandler<string>(this.Handle)` call. At runtime, the RouteBuilder expects a delegate with exactly 2 or 3 parameters (message, context, optionally CancellationToken). The generated code passes `this.Handle` as a method group -- if the method has 4 parameters, the method group conversion to the `Action<TInput, IWorkflowContext, CancellationToken>` delegate would fail at compile time with CS0123. So the failure IS caught, but by the C# compiler with an unhelpful error message rather than by a descriptive generator diagnostic.
**Ideal state**: The generator should emit a diagnostic (e.g., "Handler has too many parameters") for methods with more than 3 parameters, giving users a clear, actionable error message rather than a cryptic method-group conversion failure.
**Feasibility**: Feasible
**Feasibility rationale**: Adding a `Parameters.Length > 3` check with a new diagnostic descriptor is straightforward. No architectural changes required. Low effort, high clarity gain.

### Gap 3: No Diagnostic for Third Parameter That Is Not CancellationToken

**Category**: escape path
**Current state**: In `SemanticAnalyzer.AnalyzeHandler` (line 492-493), the check `hasCancellationToken = methodSymbol.Parameters.Length >= 3 && methodSymbol.Parameters[2].Type.ToDisplayString() == CancellationTokenTypeName` silently sets `hasCancellationToken = false` when the third parameter is not a `CancellationToken`. A handler like `void Handle(string msg, IWorkflowContext ctx, int someOtherParam)` would be accepted with `hasCancellationToken = false`, and the generator would emit `AddHandler<string>(this.Handle)`. The method-group conversion would then fail at compile time because no `AddHandler` overload accepts `Action<string, IWorkflowContext, int>`. The user gets a generic C# compiler error rather than an informative diagnostic.
**Ideal state**: When a third parameter exists but is not `CancellationToken`, the generator should emit a warning diagnostic such as "Third parameter of handler should be CancellationToken; other types are not supported."
**Feasibility**: Feasible
**Feasibility rationale**: Simple conditional check with a new diagnostic descriptor. No architectural change needed.

### Gap 4: Duplicate Input Type Handlers Produce Runtime Exception, Not Compile-Time Diagnostic

**Category**: escape path
**Current state**: If two `[MessageHandler]` methods on the same executor handle the same input message type (e.g., two methods both taking `string` as the first parameter), the generator will produce two `.AddHandler<string>(this.Method1)` and `.AddHandler<string>(this.Method2)` calls. The `RouteBuilder.AddHandlerInternal` (line 51-89 of RouteBuilder.cs) throws `ArgumentException` ("A handler for message type X is already registered") at runtime during protocol configuration. The user receives a runtime exception instead of a compile-time diagnostic.
**Ideal state**: The generator should detect duplicate input type registrations during `CombineHandlerMethodResults` and emit a compile-time error diagnostic, preventing the runtime failure.
**Feasibility**: Feasible
**Feasibility rationale**: During `CombineHandlerMethodResults`, the generator already collects all handlers per class. A `HashSet<string>` tracking `InputTypeName` would detect duplicates. Low-effort change with high impact for developer experience.

### Gap 5: Plan/Implementation Naming Mismatch Not Surfaced to Consumers (YieldsMessageAttribute vs YieldsOutputAttribute)

**Category**: scope gap
**Current state**: The plan (AC-5) specifies `YieldsMessageAttribute`, but the actual implementation uses `YieldsOutputAttribute` (at `dotnet/src/Microsoft.Agents.AI.Workflows/Attributes/YieldsOutputAttribute.cs`). The codebase-snapshot.md section 4 documents this discrepancy. However, if the design document uses the plan's terminology, users consulting the plan and the actual API will see different names, causing confusion during migration.
**Ideal state**: The design document should explicitly note the name change with a redirect: "`YieldsMessageAttribute` was renamed to `YieldsOutputAttribute` to align with the `YieldsOutput<T>()` fluent API on `ProtocolBuilder`." Any migration guide should reference the actual name.
**Feasibility**: Feasible
**Feasibility rationale**: Documentation-only change. The actual implementation is correct; only the plan reference needs updating.

### Gap 6: Generated Code Does Not Explicitly Register Return-Type Yield Types (Relies on Runtime Auto-Yield)

**Category**: unstated assumption
**Current state**: When a handler returns `ValueTask<TResult>`, the generator registers it via `AddHandler<TInput, TResult>(this.Method)`, which records `TResult` as an output type in the `RouteBuilder._outputTypes` dictionary. At `ProtocolBuilder.Build()` time (line 167-169 of ProtocolBuilder.cs), if `ExecutorOptions.AutoYieldOutputHandlerResultObject` is true (the default), the `DefaultOutputTypes` from the router are unioned into `yieldTypes`. So the yield registration of return types happens implicitly at runtime via `AutoYieldOutputHandlerResultObject`, not explicitly in the generated code.

However, `ShouldGenerateYieldedOutputRegistrations` in `ExecutorInfo` (line 37) returns `true` when any handler `HasOutput` (line 72-75), which triggers `GenerateConfigureYieldTypes()`. But `GenerateConfigureYieldTypes()` only emits `.YieldsOutput<T>()` for explicit `handler.YieldTypes` and `info.ClassYieldTypes` -- not for the handler's return type (`OutputTypeName`). If a handler has a return type but no explicit `[MessageHandler(Yield = ...)]` and no class-level `[YieldsOutput]`, the `GenerateConfigureYieldTypes` method iterates over empty collections, generating nothing. The `ShouldGenerateYieldedOutputRegistrations` guard still evaluates true, but the method body is a no-op. This is functionally correct because the runtime handles it, but it means the compile-time protocol declaration is incomplete: users who set `AutoYieldOutputHandlerResultObject = false` would get no yield type registration for return types, and protocol validation would reject yields of those types.
**Ideal state**: Either (a) the generated code should explicitly emit `.YieldsOutput<TResult>()` for handler return types so the protocol is self-documenting and independent of `ExecutorOptions`, or (b) the design document should explicitly note this runtime dependency and warn that `AutoYieldOutputHandlerResultObject = false` requires explicit `[YieldsOutput]` attributes.
**Feasibility**: Feasible
**Feasibility rationale**: Adding `outputTypeName` to the yield type emission in `GenerateConfigureYieldTypes()` is a small code change in `SourceBuilder.cs`. However, this would diverge from the current behavior where the runtime auto-yield and the explicit yield attributes are the two orthogonal mechanisms. The safer path is option (b): document the dependency.

### Gap 7: No Integration Test Verifying Behavioral Equivalence Between Source-Generated and Reflected Routes

**Category**: test type mismatch
**Current state**: AC-16 requires "Port existing ReflectingExecutor test cases to use [MessageHandler]" and "Verify generated routes match reflection-discovered routes." The existing test suite at `dotnet/tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/` contains 67 test methods that verify the generator's output structurally (checking generated source text). There are no tests that actually build and run both the source-generated and reflection-based executors side-by-side and compare their runtime behavior (protocol configuration, route resolution, message handling). The file `dotnet/tests/Microsoft.Agents.AI.Workflows.UnitTests/ReflectionSmokeTest.cs` exists but tests only the reflection path. No file exists that instantiates a source-generated executor AND a ReflectingExecutor with the same handlers and asserts identical routing behavior.
**Ideal state**: An integration test that defines an executor with both `[MessageHandler]` attributes and `IMessageHandler<T>` interface implementations, builds one via source generation and one via reflection, sends the same messages, and asserts identical routing and output behavior.
**Feasibility**: Partially feasible
**Feasibility rationale**: Source generator tests typically use `CSharpGeneratorDriver` which produces source text, not compiled assemblies. A true runtime comparison test would need to compile and load the generated code, instantiate the executor, and exercise it. This is doable via in-memory compilation but adds significant test infrastructure complexity. A pragmatic alternative: a manually-curated set of test cases that verify specific behavioral equivalences (route count, handler delegate types, type registrations) by comparing the generated source text against known-good baseline output from the reflection path.

### Gap 8: ReflectingExecutor Registers Handler Output Types Conditionally on AutoSend/AutoYield Options; Source Generator Does Not

**Category**: sibling vulnerability
**Current state**: `ReflectingExecutor.ConfigureProtocol` (lines 48-58 of `ReflectingExecutor.cs`) conditionally registers output types as send/yield types based on `Options.AutoSendMessageHandlerResultObject` and `Options.AutoYieldOutputHandlerResultObject`. The source generator does NOT generate any code that checks these options; it relies entirely on the runtime `ProtocolBuilder.Build()` method to apply these options. This is functionally correct because `ProtocolBuilder.Build()` applies the same options at build time. However, this means the behavior has a hidden dependency: the generated `ConfigureProtocol` method does not explicitly declare all types it will use. If `ProtocolBuilder.Build()` behavior ever changes (e.g., the auto-registration is moved to a different stage), the source-generated path and the reflection path could silently diverge.
**Ideal state**: The design document should explicitly note that the source generator delegates auto-send/auto-yield registration to `ProtocolBuilder.Build()` and that any changes to `ProtocolBuilder.Build()` must be validated against both paths.
**Feasibility**: Feasible
**Feasibility rationale**: This is a documentation/design-note addition, not a code change. Attempting to replicate the runtime option checks in generated code would require the generator to have access to `ExecutorOptions` at compile time, which is not possible since options are runtime configuration.

### Gap 9: No Validation That Executor<TInput> or Executor<TInput, TOutput> Subclasses Do Not Use [MessageHandler]

**Category**: escape path
**Current state**: The `Executor<TInput>` and `Executor<TInput, TOutput>` base classes (lines 382-423 of `Executor.cs`) already override `ConfigureProtocol` and register their own handler via `AddHandler`. If a user creates a class like `public partial class MyExecutor : Executor<string>` and adds `[MessageHandler]` methods, the generator would detect that `HasManualConfigureProtocol` is true (because `Executor<TInput>` defines `ConfigureProtocol`). This would trigger MAFGENWF006 (Info level: "ConfigureProtocol already defined") and skip generation. This is correct behavior, but the diagnostic severity is only Info, meaning users might not notice it. They would expect their `[MessageHandler]` methods to work, but they would be silently ignored.
**Ideal state**: When a class inherits from `Executor<TInput>` or `Executor<TInput, TOutput>` (which provide their own `ConfigureProtocol`), the diagnostic should be Warning or Error level rather than Info, since the user clearly intended to use `[MessageHandler]` but it will be silently ignored. The message should guide them: "Inherit from Executor directly and use [MessageHandler] instead of inheriting from Executor<TInput>."
**Feasibility**: Feasible
**Feasibility rationale**: This requires changing the diagnostic severity from Info to Warning for this specific scenario, or adding a new diagnostic that distinguishes "user manually defined ConfigureProtocol" from "base class provides ConfigureProtocol." Moderate effort: the generator would need to distinguish between the two cases by checking if the `ConfigureProtocol` override is on the direct base class or on an intermediate class.

### Gap 10: Hint Name Generation for Generics Uses Approximation

**Category**: version drift / scope gap
**Current state**: `ExecutorRouteGenerator.GetHintName` (line 153-155 of `ExecutorRouteGenerator.cs`) computes the generic parameter count approximation using `info.GenericParameters!.Length - 2` (subtracting 2 for the `<` and `>` characters). For a single type parameter like `<T>`, this gives `1` (correct: `"<T>".Length - 2 = 1`). For `<T, U>`, this gives `3` (incorrect: actual count is 2, but `"<T, U>".Length - 2 = 4`). Actually the string would be `"<T, U>"` which is length 6, minus 2 = 4. This is used only for generating a unique file name, so a wrong count does not cause functional issues, but it could theoretically collide with another class if two generic classes in the same namespace have names that differ only in their type parameter count. This is extremely unlikely in practice.
**Ideal state**: Use `info.GenericParameters.Count(c => c == ',') + 1` or the actual `TypeParameters.Length` from the symbol, which is precise.
**Feasibility**: Feasible
**Feasibility rationale**: Trivial code change. The `GenericParameters` string could be replaced with a `GenericParameterCount` integer on `ExecutorInfo`, or the count could be computed from the string more precisely.

### Gap 11: No Migration Guide Document Referenced in [Obsolete] Message

**Category**: observability gap
**Current state**: AC-13 specifies the obsolete message should say "See migration guide." The actual [Obsolete] message on `ReflectingExecutor<T>` (line 21-22 of `ReflectingExecutor.cs`) says "Use [MessageHandler] attribute on methods in a partial class deriving from Executor. This type will be removed in a future version." -- it omits "See migration guide." This matches what exists in the codebase. However, no migration guide document was found in the repository. If a user reads the obsolete message, they have no guide to follow.
**Ideal state**: Either (a) create a migration guide document and reference it in the [Obsolete] message, or (b) the design should acknowledge that the migration guide is out of scope and update AC-13 accordingly.
**Feasibility**: Feasible
**Feasibility rationale**: Writing a migration guide is standard documentation work. Referencing it from the [Obsolete] attribute is a one-line change.

### Gap 12: SendsMessage/YieldsOutput on Method-Level Not Exercised by Generator for Protocol-Only Classes

**Category**: escape path
**Current state**: Both `SendsMessageAttribute` and `YieldsOutputAttribute` have `AttributeTargets.Class | AttributeTargets.Method`. Pipeline 2 and Pipeline 3 in `ExecutorRouteGenerator.cs` (lines 40-53) use `predicate: static (node, _) => node is ClassDeclarationSyntax`, meaning they only detect these attributes on classes, not on methods. Method-level `[SendsMessage]`/`[YieldsOutput]` are handled through `GetAttributeTypeArrays` in `SemanticAnalyzer` only when a `[MessageHandler]` method is present. For a class that uses `Executor<TInput>` (which has its own `ConfigureProtocol`) and adds `[SendsMessage(typeof(Foo))]` on individual methods (not on the class), the generator pipeline would not pick up those method-level attributes because: (a) Pipeline 2/3 only look at classes, (b) the `[MessageHandler]` pipeline would not fire because there are no `[MessageHandler]` methods. The method-level attributes on non-`[MessageHandler]` methods would be silently ignored by the generator.

However, at runtime, `ReflectingExecutor.ConfigureProtocol` does scan for these via `AddMethodAttributeTypes`, and the `Executor<TInput>` base class does call `AddMethodAttributeTypes(handlerDelegate.Method)` which would pick up method-level attributes on the `HandleAsync` method. So for `Executor<TInput>` subclasses, method-level attributes on the `HandleAsync` method ARE picked up at runtime. The gap is only for methods that are NOT `HandleAsync` and NOT `[MessageHandler]` -- which would be unusual but possible.
**Ideal state**: Document that method-level `[SendsMessage]`/`[YieldsOutput]` attributes are only processed on `[MessageHandler]`-attributed methods or on the single `HandleAsync` method of `Executor<TInput>` subclasses. Other methods' attributes are not picked up.
**Feasibility**: Feasible
**Feasibility rationale**: Documentation clarification. Extending the generator to scan all methods for `[SendsMessage]`/`[YieldsOutput]` would be architecturally complex and would blur the boundary between source generation and reflection.

### Gap 13: Partial Class Across Multiple Files Not Explicitly Tested

**Category**: test type mismatch
**Current state**: All unit tests define the executor class in a single source string. In real projects, partial classes are commonly split across multiple files. The `ForAttributeWithMetadataName` API handles this correctly (it works at the semantic model level, not the syntax level), and `IsPartialClass` checks `DeclaringSyntaxReferences` across all syntax trees. However, no test verifies this explicitly -- e.g., a test with two separate source strings where the first file has `partial class MyExecutor : Executor { }` and the second has `partial class MyExecutor { [MessageHandler] void Handle(string m, IWorkflowContext ctx) {} }`.
**Ideal state**: At least one test with a multi-file partial class split to verify the generator correctly discovers handlers across files.
**Feasibility**: Feasible
**Feasibility rationale**: The `CSharpGeneratorDriver` test infrastructure already supports multiple syntax trees. Adding a test with two source strings is straightforward.

## Summary Table

| # | Gap | Category | Impact | Feasibility | Specific constraint (if infeasible) |
|---|-----|----------|--------|-------------|--------------------------------------|
| 1 | Roslyn version drift (plan 4.8.0 vs actual 4.4.0) | version drift | Low (plan-only; impl is correct) | Feasible | N/A |
| 2 | 4+ parameter handlers silently accepted | escape path | Medium (confusing compiler error) | Feasible | N/A |
| 3 | Non-CancellationToken third parameter silently ignored | escape path | Medium (confusing compiler error) | Feasible | N/A |
| 4 | Duplicate input type handlers cause runtime not compile-time error | escape path | High (runtime crash vs build error) | Feasible | N/A |
| 5 | YieldsMessage vs YieldsOutput naming mismatch | scope gap | Low (documentation clarity) | Feasible | N/A |
| 6 | Return-type yield registration deferred to runtime | unstated assumption | Medium (breaks with AutoYield=false) | Feasible | N/A |
| 7 | No runtime behavioral equivalence integration test | test type mismatch | High (migration correctness) | Partially feasible | Requires in-memory compilation infrastructure |
| 8 | Source generator delegates auto-send/yield to runtime; undocumented dependency | sibling vulnerability | Low (documented assumption sufficient) | Feasible | N/A |
| 9 | Executor<T> subclass [MessageHandler] silently ignored at Info level | escape path | High (user intent silently discarded) | Feasible | N/A |
| 10 | Hint name generic parameter count approximation | version drift | Very Low (cosmetic, extremely unlikely collision) | Feasible | N/A |
| 11 | No migration guide exists despite [Obsolete] message implying one | observability gap | Medium (migration friction) | Feasible | N/A |
| 12 | Method-level SendsMessage/YieldsOutput on non-handler methods ignored | escape path | Low (unusual usage pattern) | Feasible | N/A |
| 13 | Multi-file partial class not explicitly tested | test type mismatch | Medium (real-world usage pattern untested) | Feasible | N/A |

## Practical Ceiling

For a Roslyn source generator of this scope, the practical quality ceiling is bounded by:

1. **Compile-time vs runtime boundary**: The generator operates on syntax and semantic models at compile time and cannot access runtime configuration (like `ExecutorOptions`). This means some validation must inherently occur at runtime. The design correctly handles this by delegating `AutoSendMessage`/`AutoYieldOutput` to `ProtocolBuilder.Build()`, but this creates an irreducible coupling between the generated code and the runtime builder.

2. **Roslyn API stability**: The generator depends on the Roslyn `ForAttributeWithMetadataName` API and `IIncrementalGenerator` contract. Changes to Roslyn's behavior in future SDK versions could affect the generator without any code changes. The 4.4.0 minimum version choice provides broad compatibility but means the generator cannot use newer Roslyn APIs.

3. **Test depth ceiling**: Full behavioral equivalence testing between source-generated and reflection-based paths would require compiling and executing generated code in test harness, which is architecturally expensive. The current structural verification (comparing generated source text) covers most cases but cannot catch subtle runtime behavioral differences.

**Residual risks that must be accepted:**
- Runtime options (`ExecutorOptions`) cannot be validated at compile time
- Exact behavioral parity between ReflectingExecutor and source-generated paths can only be fully verified through runtime integration tests, not source-text comparison
- Users who split partial classes across many files may encounter incremental caching edge cases that are difficult to reproduce in unit tests
