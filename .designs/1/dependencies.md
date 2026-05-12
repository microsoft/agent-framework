# dependencies.md -- Dependency Graph

## Component Dependencies (Code-Level)

### Runtime Components (Microsoft.Agents.AI.Workflows)

```
Executor (abstract class)
  ^
  |-- ProtocolBuilder (fluent config)
  |     |-- RouteBuilder (handler registration)
  |     |-- SendsMessage<T>() (type declaration)
  |     |-- YieldsOutput<T>() (type declaration)
  |
  |-- MessageHandlerAttribute (method-level attribute)
  |-- SendsMessageAttribute (class/method-level attribute)
  |-- YieldsOutputAttribute (class/method-level attribute)
  |
  |-- ReflectingExecutor<T> [Obsolete] (reflection-based alternative)
       |-- IMessageHandler<T> [Obsolete] (interface-based routing)
```

**Dependency direction:** User executor classes -> Executor (base) + Attributes -> ProtocolBuilder -> RouteBuilder. No circular dependencies.

### Generator Components (Microsoft.Agents.AI.Workflows.Generators)

```
ExecutorRouteGenerator (IIncrementalGenerator)
  |
  |-- Pipeline 1: ForAttributeWithMetadataName("MessageHandlerAttribute")
  |     |-- SemanticAnalyzer.AnalyzeHandlerMethod()
  |     |     |-- HandlerInfo (model)
  |     |     |-- MethodAnalysisResult (model)
  |     |     |-- DiagnosticInfo (model)
  |     |     |-- DiagnosticLocationInfo (model)
  |     |     |-- HandlerSignatureKind (enum)
  |     |
  |     |-- SemanticAnalyzer.CombineHandlerMethodResults()
  |           |-- AnalysisResult (model)
  |           |-- ExecutorInfo (model)
  |           |-- DiagnosticDescriptors (diagnostic definitions)
  |
  |-- Pipeline 2: ForAttributeWithMetadataName("SendsMessageAttribute")
  |     |-- SemanticAnalyzer.AnalyzeClassProtocolAttribute()
  |           |-- ClassProtocolInfo (model)
  |           |-- ProtocolAttributeKind (enum)
  |
  |-- Pipeline 3: ForAttributeWithMetadataName("YieldsOutputAttribute")
  |     |-- SemanticAnalyzer.AnalyzeClassProtocolAttribute() [same as Pipeline 2]
  |
  |-- CombineAllResults() (merge pipelines)
  |     |-- AnalysisResult (combined)
  |
  |-- SourceBuilder.Generate()
        |-- ExecutorInfo (input)
        |-- HandlerInfo (input)
        |-- ImmutableEquatableArray<T> (collection wrapper)
```

**Dependency direction:** ExecutorRouteGenerator -> SemanticAnalyzer -> Models -> DiagnosticDescriptors. SourceBuilder <- ExecutorInfo. No circular dependencies.

### Cross-Project Dependencies

```
Microsoft.Agents.AI.Workflows.Generators (netstandard2.0)
  |
  |-- [analyzer reference, compile-time only]
  v
Microsoft.Agents.AI.Workflows (net8.0, netstandard2.0)
  |
  |-- [ProjectReference]
  v
Microsoft.Agents.AI.Abstractions
Microsoft.Agents.AI
```

```
Microsoft.Agents.AI.Workflows.Generators.UnitTests (test project)
  |
  |-- [ProjectReference] -> Microsoft.Agents.AI.Workflows.Generators
  |-- [InternalsVisibleTo from] Microsoft.Agents.AI.Workflows
```

**Note:** The generator project does NOT have a compile-time dependency on the Workflows project. It discovers attribute metadata by fully-qualified name string (e.g., `"Microsoft.Agents.AI.Workflows.MessageHandlerAttribute"` in ExecutorRouteGenerator.cs:24). This is the correct pattern for Roslyn generators -- they must not reference the target assembly.

---

## Component Build Order (Critical Path)

| Order | Component | TFM | Depends On | Blocks |
|-------|-----------|-----|------------|--------|
| 1 | Microsoft.Agents.AI.Abstractions | net8.0, netstandard2.0 | External packages | Workflows |
| 2 | Microsoft.Agents.AI | net8.0, netstandard2.0 | Abstractions | Workflows |
| 3a | Microsoft.Agents.AI.Workflows.Generators | netstandard2.0 | Roslyn 4.4.0 (NuGet) | Workflows (as analyzer), Generator tests |
| 3b | Microsoft.Agents.AI.Workflows | net8.0, netstandard2.0 | AI, Abstractions, Generators (analyzer) | Downstream consumers, Workflows tests |
| 4 | Microsoft.Agents.AI.Workflows.Generators.UnitTests | net8.0+ | Generators, Workflows (InternalsVisibleTo) | CI gate |

**Critical path:** Abstractions -> AI -> Generators -> Workflows -> Tests

Steps 3a and 3b have a dependency: Workflows depends on Generators as an analyzer. However, MSBuild handles this correctly via the `OutputItemType="Analyzer"` reference. The generator must build FIRST so its DLL is available for the Workflows compilation.

The `SkipIncompatibleBuild.targets` file in the Generators project handles cross-platform build scenarios where the generator cannot be compiled (e.g., if the Roslyn SDK is unavailable).

---

## Circular Dependency Check

**Result: No circular dependencies.**

Verification:
1. **Generator -> Workflows:** NO. Generator references Workflows types by string name only (ExecutorRouteGenerator.cs:24-26), not by project reference.
2. **Workflows -> Generator:** YES, but as analyzer only (OutputItemType="Analyzer", ReferenceOutputAssembly="false"). This is a build-time-only dependency, not a compile-time reference dependency.
3. **Models -> SemanticAnalyzer:** NO. Models are plain records with no behavior.
4. **SemanticAnalyzer -> SourceBuilder:** NO. These are independent: SemanticAnalyzer produces AnalysisResult, SourceBuilder consumes ExecutorInfo. The connection is through ExecutorRouteGenerator (the orchestrator).
5. **DiagnosticDescriptors -> SemanticAnalyzer:** One-way. SemanticAnalyzer references DiagnosticDescriptors; DiagnosticDescriptors does not reference SemanticAnalyzer.

---

## Critical Path Risks

| Risk | Severity | Component | Mitigation |
|------|----------|-----------|------------|
| Roslyn version incompatibility | Medium | Generators | Pinned to 4.4.0; comment in .csproj documents rationale; SkipIncompatibleBuild.targets handles unsupported platforms |
| Generator build failure blocks Workflows | High | Generators -> Workflows | SkipIncompatibleBuild.targets allows Workflows to build without generator on unsupported platforms |
| InternalsVisibleTo coupling | Low | Workflows -> Generator tests | Only affects test project; production code unaffected |
| TFM mismatch (generator=netstandard2.0, host=net8.0) | Low | Generators | GlobalPropertiesToRemove="TargetFramework" in Workflows .csproj prevents MSBuild from passing wrong TFM |
| Attribute name string coupling | Medium | Generator <-> Workflows | Generator uses hardcoded fully-qualified attribute names (ExecutorRouteGenerator.cs:24-26). If attribute namespace changes, generator silently stops working. Mitigated by being in the same repo with CI/CD. |

---

## Dependency Summary

The dependency graph is clean with no circular dependencies. The critical path runs through the Generators project (must build before Workflows), but this is handled by standard MSBuild analyzer reference patterns. The only significant coupling is the string-based attribute name matching between the generator and the Workflows attribute definitions, which is the standard pattern for Roslyn generators and is mitigated by co-location in the same repository.
