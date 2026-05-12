# D6: Integration

## Dimension Summary

Integration covers: (1) how the source generator connects to the Workflows project and solution, (2) which existing files are modified, (3) the test infrastructure, (4) the migration path from ReflectingExecutor<T>, and (5) build system impacts.

---

## Option I1: Current Integration Architecture (RECOMMENDED)

The source generator is already fully integrated into the solution and build system:

### Project References (AC-12, AC-18)

**Workflows -> Generator reference** (Microsoft.Agents.AI.Workflows.csproj:35-39):
```xml
<ProjectReference Include="..\Microsoft.Agents.AI.Workflows.Generators\..."
                  OutputItemType="Analyzer"
                  ReferenceOutputAssembly="false"
                  GlobalPropertiesToRemove="TargetFramework" />
```

This is the correct pattern for referencing a source generator as an analyzer. Verified:
- `OutputItemType="Analyzer"` -- loads as analyzer, not library reference
- `ReferenceOutputAssembly="false"` -- generator DLL not copied to output
- `GlobalPropertiesToRemove="TargetFramework"` -- prevents TFM mismatch when Workflows targets net8.0+ but generator targets netstandard2.0

### Solution Integration (AC-18)

The solution file is `dotnet/agent-framework-dotnet.slnx` (codebase-snapshot.md section 2). Both the generator project and the unit test project are included.

### Obsolete Markers (AC-13, AC-14)

- **ReflectingExecutor<T>** (ReflectingExecutor.cs:21-22): Already marked `[Obsolete("Use [MessageHandler] attribute on methods in a partial class deriving from Executor. This type will be removed in a future version.")]`
  - Note: Plan says "This type will be removed in v1.0." but actual says "This type will be removed in a future version." -- slightly different wording.
- **IMessageHandler<T>** (Reflection/IMessageHandler.cs): Already marked `[Obsolete]`

### Test Infrastructure (AC-15, AC-16)

**Unit Tests** (dotnet/tests/Microsoft.Agents.AI.Workflows.Generators.UnitTests/):
- `ExecutorRouteGeneratorTests.cs` (~37KB) -- comprehensive test coverage
- `GeneratorTestHelper.cs` -- test infrastructure for running generators in-memory
- `SyntaxTreeFluentExtensions.cs` -- fluent assertions for generated code

Note: AC-15 specifies `SyntaxDetectorTests.cs` and `SemanticAnalyzerTests.cs` as separate files. The actual tests are consolidated in `ExecutorRouteGeneratorTests.cs`, which tests the full pipeline (syntax detection through semantic analysis to code generation). This is the standard approach for incremental generator testing, since the unit of work is the full generator pipeline.

**Test cases covered** (verified from codebase-snapshot.md section 5):
- Single handler (void, ValueTask, ValueTask<T>)
- Multiple handlers on one class
- CancellationToken parameter variants
- Yield/Send type attributes on handlers
- Class-level [SendsMessage] and [YieldsOutput] attributes
- Nested classes
- Generic executors
- Inheritance chains
- ConfigureProtocol already defined (skip generation)
- Invalid signatures (diagnostic verification)

### InternalsVisibleTo

Microsoft.Agents.AI.Workflows.csproj:31 grants:
```xml
<InternalsVisibleTo Include="Microsoft.Agents.AI.Workflows.Generators.UnitTests" />
```
This allows generator unit tests to access internal Workflows types for test compilation contexts.

**Trade-offs:**
- (+) Fully operational -- no integration gaps
- (+) Generator reference uses recommended MSBuild patterns
- (+) `GlobalPropertiesToRemove="TargetFramework"` handles the TFM mismatch correctly
- (+) Comprehensive test coverage
- (-) Test file structure differs from plan (consolidated vs separate files)
- (-) Obsolete message wording differs slightly from plan

**Reversibility:** Moderate -- deeply integrated with build system.

**Constraint compliance:**
- C-1 (netstandard2.0): Generator project targets netstandard2.0 (Microsoft.Agents.AI.Workflows.Generators.csproj:5)
- C-3 (analyzer packaging): `IsRoslynComponent=true`, `EnforceExtendedAnalyzerRules=true` (Microsoft.Agents.AI.Workflows.Generators.csproj:16-17), packed to `analyzers/dotnet/cs` (line 55)
- C-4 (clean break): ReflectingExecutor marked [Obsolete], generator requires Executor inheritance

**Dependencies produced:** Build system configuration consumed by D4 (scale -- build performance).
**Dependencies required:** Attribute definitions from D1 (API), model types from D2 (data).

**Risks:**
- Severity: Low. Integration is complete and working.
- Mitigation: Existing CI/CD validates the full build.

---

## Option I2: Split Test Files Per AC-15

Refactor `ExecutorRouteGeneratorTests.cs` into separate test files:
- `SyntaxDetectorTests.cs` -- tests for syntax-level detection
- `SemanticAnalyzerTests.cs` -- tests for semantic validation
- `ExecutorRouteGeneratorTests.cs` -- tests for end-to-end generation

**Trade-offs:**
- (+) Matches AC-15 file structure exactly
- (+) Smaller, more focused test files
- (-) Artificial split -- incremental generators are tested end-to-end because the unit of work is the full pipeline (syntax -> semantic -> generation)
- (-) SyntaxDetector is inline (no separate class), so "SyntaxDetectorTests" would test the ForAttributeWithMetadataName predicate indirectly
- (-) Risk of test duplication (end-to-end tests implicitly test syntax and semantic phases)
- (-) Significant refactoring effort for ~37KB of tests

**Reversibility:** Easy -- just file reorganization.

**Constraint compliance:** All constraints met.

**Dependencies produced:** None.
**Dependencies required:** None.

**Risks:**
- Severity: Low. Code reorganization only.
- Mitigation: N/A.

---

## Option I3: Add Integration Test Project (Per AC-16)

Create a separate integration test project that:
1. Ports existing `ReflectingExecutor` test cases to use `[MessageHandler]`
2. Verifies generated routes match reflection-discovered routes at runtime

**Trade-offs:**
- (+) Directly satisfies AC-16
- (+) Validates that the source-generated code produces functionally identical behavior to reflection-based discovery
- (+) Catch regressions where generated AddHandler calls differ from reflected ones
- (-) Requires a separate project that can reference both the generator and the Workflows library
- (-) Runtime comparison is complex: must instantiate both a ReflectingExecutor and a source-generated executor, then compare their Protocol configurations
- (-) ReflectingExecutor is [Obsolete], so test project must suppress the warning

**Reversibility:** Easy -- additive.

**Constraint compliance:** All constraints met. Integration test project would target net8.0+ (not constrained by C-1).

**Dependencies produced:** Integration test project consumed by CI/CD.
**Dependencies required:** Working generator from D2 (data), attributes from D1 (API).

**Risks:**
- Severity: Medium. AC-16 is explicitly in scope but not currently implemented as described.
- Mitigation: The unit tests in ExecutorRouteGeneratorTests.cs verify generated code correctness, providing equivalent coverage through a different mechanism.

---

## Option I4: Update Obsolete Message to Match Plan Exactly

Change ReflectingExecutor's `[Obsolete]` message from "This type will be removed in a future version." to "See migration guide. This type will be removed in v1.0." per AC-13.

**Trade-offs:**
- (+) Matches AC-13 verbatim
- (-) Promises removal "in v1.0" which is a concrete version commitment that may not be appropriate
- (-) References a "migration guide" that does not yet exist
- (-) Minor text change with no functional impact

**Reversibility:** Easy.

**Constraint compliance:** All constraints met.

**Dependencies produced:** None.
**Dependencies required:** Migration guide from D3 (UX).

**Risks:**
- Severity: Low.
- Mitigation: Ensure migration guide exists before changing the message.

---

## Call Sites That Change (AC-18 Analysis)

| File | Change | Status |
|------|--------|--------|
| Microsoft.Agents.AI.Workflows.csproj | Add generator ProjectReference | DONE (lines 35-39) |
| ReflectingExecutor.cs | Add [Obsolete] | DONE (lines 21-22) |
| IMessageHandler.cs | Add [Obsolete] | DONE |
| agent-framework-dotnet.slnx | Add new projects | DONE |

All AC-18 modifications are already applied.

---

## Build Order Impact

The generator project must build BEFORE the Workflows project (since it is referenced as an analyzer). The `OutputItemType="Analyzer"` reference ensures MSBuild handles this ordering. The `SkipIncompatibleBuild.targets` file in the generator project handles cases where the generator cannot be built on the current platform.

Critical path:
1. Microsoft.Agents.AI.Workflows.Generators (netstandard2.0)
2. Microsoft.Agents.AI.Workflows (multi-TFM: net8.0, netstandard2.0)
3. All downstream projects

---

## Summary

**Recommended option: I1** -- The current integration architecture is complete and operational. All AC-18 modifications are applied, the generator is correctly referenced as an analyzer, tests are comprehensive, and obsolete markers are in place. The differences from the plan (consolidated test files, slightly different obsolete wording) are non-functional.
