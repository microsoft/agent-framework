# Source Generator Best Practices Review

This document reviews the Workflow Executor Route Source Generator implementation against the official Roslyn Source Generator Cookbook best practices from the dotnet/roslyn repository.

## Reference Documentation

- [Source Generators Cookbook](https://github.com/dotnet/roslyn/blob/main/docs/features/source-generators.cookbook.md)
- [Incremental Generators Cookbook](https://github.com/dotnet/roslyn/blob/main/docs/features/incremental-generators.cookbook.md)

---

## Executive Summary

| Category | Status | Priority |
|----------|--------|----------|
| Generator Type | PASS | - |
| Attribute-Based Detection | FAIL | HIGH |
| Model Value Equality | FAIL | HIGH |
| Collection Equality | FAIL | HIGH |
| Symbol/SyntaxNode Storage | PASS | - |
| Code Generation Approach | PASS | - |
| Diagnostics | PASS | - |
| Pipeline Efficiency | FAIL | MEDIUM |
| CancellationToken Handling | PARTIAL | LOW |

**Overall Assessment**: The generator follows several best practices but has critical performance issues that should be addressed before production use. The most significant issue is not using `ForAttributeWithMetadataName`, which the Roslyn team states is "at least 99x more efficient" than `CreateSyntaxProvider`.

---

## Detailed Analysis

### 1. Generator Interface Selection

**Best Practice**: Use `IIncrementalGenerator` instead of the deprecated `ISourceGenerator`.

**Our Implementation**: PASS

```csharp
// ExecutorRouteGenerator.cs:19
public sealed class ExecutorRouteGenerator : IIncrementalGenerator
```

The generator correctly implements `IIncrementalGenerator`, the recommended interface for new generators.

---

### 2. Attribute-Based Detection with ForAttributeWithMetadataName

**Best Practice**: Use `ForAttributeWithMetadataName()` for attribute-based discovery.

> "This utility method is at least 99x more efficient than `SyntaxProvider.CreateSyntaxProvider`, and in many cases even more efficient."
> — Roslyn Incremental Generators Cookbook

**Our Implementation**: FAIL (HIGH PRIORITY)

```csharp
// ExecutorRouteGenerator.cs:25-30
var executorCandidates = context.SyntaxProvider
    .CreateSyntaxProvider(
        predicate: static (node, _) => SyntaxDetector.IsExecutorCandidate(node),
        transform: static (ctx, ct) => SemanticAnalyzer.Analyze(ctx, ct, out _))
```

**Problem**: We use `CreateSyntaxProvider` with manual attribute detection in `SyntaxDetector`. This requires the generator to examine every syntax node in the compilation, whereas `ForAttributeWithMetadataName` uses the compiler's built-in attribute index for O(1) lookup.

**Recommended Fix**:

```csharp
var executorCandidates = context.SyntaxProvider
    .ForAttributeWithMetadataName(
        fullyQualifiedMetadataName: "Microsoft.Agents.AI.Workflows.MessageHandlerAttribute",
        predicate: static (node, _) => node is MethodDeclarationSyntax,
        transform: static (ctx, ct) => AnalyzeMethodWithAttribute(ctx, ct))
    .Collect()
    .SelectMany((methods, _) => GroupByContainingClass(methods));
```

**Impact**: Current approach causes IDE lag on every keystroke in large projects.

---

### 3. Model Value Equality (Records vs Classes)

**Best Practice**: Use `record` types for pipeline models to get automatic value equality.

> "Use `record`s, rather than `class`es, so that value equality is generated for you."
> — Roslyn Incremental Generators Cookbook

**Our Implementation**: FAIL (HIGH PRIORITY)

```csharp
// HandlerInfo.cs:28
internal sealed class HandlerInfo { ... }

// ExecutorInfo.cs:10
internal sealed class ExecutorInfo { ... }
```

**Problem**: Both `HandlerInfo` and `ExecutorInfo` are `sealed class` types, which use reference equality by default. The incremental generator caches results based on equality comparison—when the model equals the previous run's model, regeneration is skipped. With reference equality, every analysis produces a "new" object, defeating caching entirely.

**Recommended Fix**:

```csharp
// HandlerInfo.cs
internal sealed record HandlerInfo(
    string MethodName,
    string InputTypeName,
    string? OutputTypeName,
    HandlerSignatureKind SignatureKind,
    bool HasCancellationToken,
    EquatableArray<string>? YieldTypes,
    EquatableArray<string>? SendTypes);

// ExecutorInfo.cs
internal sealed record ExecutorInfo(
    string? Namespace,
    string ClassName,
    string? GenericParameters,
    bool IsNested,
    string ContainingTypeChain,
    bool BaseHasConfigureRoutes,
    EquatableArray<HandlerInfo> Handlers,
    EquatableArray<string> ClassSendTypes,
    EquatableArray<string> ClassYieldTypes);
```

**Impact**: Without value equality, the generator regenerates code on every compilation even when nothing changed.

---

### 4. Collection Equality

**Best Practice**: Use custom equatable wrappers for collections since `ImmutableArray<T>` uses reference equality.

> "Arrays, `ImmutableArray<T>`, and `List<T>` use reference equality by default. Wrap collections with custom types implementing value-based equality."
> — Roslyn Incremental Generators Cookbook

**Our Implementation**: FAIL (HIGH PRIORITY)

```csharp
// ExecutorInfo.cs:46
public ImmutableArray<HandlerInfo> Handlers { get; }

// HandlerInfo.cs:58-63
public ImmutableArray<string>? YieldTypes { get; }
public ImmutableArray<string>? SendTypes { get; }
```

**Problem**: `ImmutableArray<T>` compares by reference, not by contents. Two arrays with identical elements are considered unequal, breaking incremental caching.

**Recommended Fix**: Create an `EquatableArray<T>` wrapper:

```csharp
internal readonly struct EquatableArray<T> : IEquatable<EquatableArray<T>>, IEnumerable<T>
    where T : IEquatable<T>
{
    private readonly ImmutableArray<T> _array;

    public EquatableArray(ImmutableArray<T> array) => _array = array;

    public bool Equals(EquatableArray<T> other)
    {
        if (_array.Length != other._array.Length) return false;
        for (int i = 0; i < _array.Length; i++)
        {
            if (!_array[i].Equals(other._array[i])) return false;
        }
        return true;
    }

    public override int GetHashCode()
    {
        var hash = new HashCode();
        foreach (var item in _array) hash.Add(item);
        return hash.ToHashCode();
    }

    // ... IEnumerable implementation
}
```

**Impact**: Same as model equality—caching is completely broken for handlers and type arrays.

---

### 5. Symbol and SyntaxNode Storage

**Best Practice**: Never store `ISymbol` or `SyntaxNode` in pipeline models.

> "Storing `ISymbol` references blocks garbage collection and roots old compilations unnecessarily. Extract only the information you need—typically string representations work well—into your equatable models."
> — Roslyn Incremental Generators Cookbook

**Our Implementation**: PASS

The models correctly store only primitive types and strings:

```csharp
// HandlerInfo.cs - stores strings, not symbols
public string MethodName { get; }
public string InputTypeName { get; }
public string? OutputTypeName { get; }

// ExecutorInfo.cs - stores strings, not symbols
public string? Namespace { get; }
public string ClassName { get; }
```

The `SemanticAnalyzer` correctly extracts string representations from symbols:

```csharp
// SemanticAnalyzer.cs:300-301
var inputType = methodSymbol.Parameters[0].Type;
var inputTypeName = inputType.ToDisplayString(SymbolDisplayFormat.FullyQualifiedFormat);
```

---

### 6. Code Generation Approach

**Best Practice**: Use `StringBuilder` for code generation, not `SyntaxNode` construction.

> "Avoid constructing `SyntaxNode`s for output; they're complex to format correctly and `NormalizeWhitespace()` is expensive. Instead, use a `StringBuilder` wrapper that tracks indentation levels."
> — Roslyn Incremental Generators Cookbook

**Our Implementation**: PASS

```csharp
// SourceBuilder.cs:17-19
public static string Generate(ExecutorInfo info)
{
    var sb = new StringBuilder();
```

The `SourceBuilder` correctly uses `StringBuilder` with manual indentation tracking.

---

### 7. Diagnostic Reporting

**Best Practice**: Use `ReportDiagnostic` for surfacing issues to users.

**Our Implementation**: PASS

```csharp
// ExecutorRouteGenerator.cs:44-50
context.RegisterSourceOutput(diagnosticsProvider, static (ctx, diagnostics) =>
{
    foreach (var diagnostic in diagnostics)
    {
        ctx.ReportDiagnostic(diagnostic);
    }
});
```

Diagnostics are well-defined with appropriate severities:

| ID | Severity | Description |
|----|----------|-------------|
| WFGEN001 | Error | Missing IWorkflowContext parameter |
| WFGEN002 | Error | Invalid return type |
| WFGEN003 | Error | Class must be partial |
| WFGEN004 | Warning | Not an Executor |
| WFGEN005 | Error | Insufficient parameters |
| WFGEN006 | Info | ConfigureRoutes already defined |
| WFGEN007 | Error | Handler cannot be static |

---

### 8. Pipeline Efficiency

**Best Practice**: Avoid duplicate work in the pipeline.

**Our Implementation**: FAIL (MEDIUM PRIORITY)

```csharp
// ExecutorRouteGenerator.cs:25-41
// Pipeline 1: Get executor candidates
var executorCandidates = context.SyntaxProvider
    .CreateSyntaxProvider(
        predicate: static (node, _) => SyntaxDetector.IsExecutorCandidate(node),
        transform: static (ctx, ct) => SemanticAnalyzer.Analyze(ctx, ct, out _))
    ...

// Pipeline 2: Get diagnostics (duplicates the same work!)
var diagnosticsProvider = context.SyntaxProvider
    .CreateSyntaxProvider(
        predicate: static (node, _) => SyntaxDetector.IsExecutorCandidate(node),
        transform: static (ctx, ct) =>
        {
            SemanticAnalyzer.Analyze(ctx, ct, out var diagnostics);
            return diagnostics;
        })
```

**Problem**: The same syntax detection and semantic analysis runs twice—once for extracting `ExecutorInfo` and once for extracting diagnostics.

**Recommended Fix**: Return both in a single pipeline:

```csharp
var analysisResults = context.SyntaxProvider
    .ForAttributeWithMetadataName(...)
    .Select((ctx, ct) => {
        var info = SemanticAnalyzer.Analyze(ctx, ct, out var diagnostics);
        return (Info: info, Diagnostics: diagnostics);
    });

// Split for different outputs
context.RegisterSourceOutput(
    analysisResults.Where(r => r.Info != null).Select((r, _) => r.Info!),
    GenerateSource);

context.RegisterSourceOutput(
    analysisResults.Where(r => r.Diagnostics.Length > 0).Select((r, _) => r.Diagnostics),
    ReportDiagnostics);
```

---

### 9. Base Type Chain Scanning

**Best Practice**: Avoid scanning indirect type relationships when possible.

> "Never scan for types that indirectly implement interfaces, inherit from base types, or acquire attributes through inheritance hierarchies. This pattern forces the generator to inspect every type's `AllInterfaces` or base-type chain on every keystroke."
> — Roslyn Incremental Generators Cookbook

**Our Implementation**: PARTIAL CONCERN

```csharp
// SemanticAnalyzer.cs:126-141
private static bool DerivesFromExecutor(INamedTypeSymbol classSymbol)
{
    var current = classSymbol.BaseType;
    while (current != null)
    {
        var fullName = current.OriginalDefinition.ToDisplayString();
        if (fullName == ExecutorTypeName || fullName.StartsWith(ExecutorTypeName + "<", ...))
        {
            return true;
        }
        current = current.BaseType;
    }
    return false;
}
```

**Analysis**: We do walk the base type chain, but this only happens after attribute filtering (classes must have `[MessageHandler]` methods). Since this is targeted to specific candidates rather than scanning all types, the performance impact is acceptable. However, if we switch to `ForAttributeWithMetadataName`, the attribute is on methods, so we'd need to check the containing class's base types—which is still targeted.

---

### 10. CancellationToken Handling

**Best Practice**: Respect `CancellationToken` in long-running operations.

**Our Implementation**: PARTIAL (LOW PRIORITY)

The `CancellationToken` is passed through to semantic model calls:

```csharp
// SemanticAnalyzer.cs:46
var classSymbol = semanticModel.GetDeclaredSymbol(classDecl, cancellationToken);
```

However, there are no explicit `cancellationToken.ThrowIfCancellationRequested()` calls in loops like `AnalyzeHandlers`. For most compilations this is fine, but very large classes with many handlers might benefit from periodic checks.

---

### 11. File Naming Convention

**Best Practice**: Use descriptive generated file names with `.g.cs` suffix.

**Our Implementation**: PASS

```csharp
// ExecutorRouteGenerator.cs:62-91
private static string GetHintName(ExecutorInfo info)
{
    // Produces: "Namespace.ClassName.g.cs" or "Namespace.Outer.Inner.ClassName.g.cs"
    ...
    sb.Append(".g.cs");
    return sb.ToString();
}
```

---

## Recommended Action Plan

### High Priority (Performance Critical)

1. **Switch to `ForAttributeWithMetadataName`**
   - Estimated impact: 99x+ performance improvement for attribute detection
   - Requires restructuring the pipeline to collect methods then group by class

2. **Convert models to records**
   - Change `HandlerInfo` and `ExecutorInfo` from `sealed class` to `sealed record`
   - Enables automatic value equality for incremental caching

3. **Implement `EquatableArray<T>`**
   - Create wrapper struct with value-based equality
   - Replace all `ImmutableArray<T>` usages in models

### Medium Priority (Efficiency)

4. **Eliminate duplicate pipeline execution**
   - Combine info extraction and diagnostic collection into single pipeline
   - Split outputs using `Where` and `Select`

### Low Priority (Polish)

5. **Add periodic cancellation checks**
   - Add `ThrowIfCancellationRequested()` in handler analysis loop
   - Only needed for extremely large classes

---

## Compliance Matrix

| Best Practice | Cookbook Reference | Status | Fix Required |
|--------------|-------------------|--------|--------------|
| Use IIncrementalGenerator | Main cookbook | PASS | No |
| Use ForAttributeWithMetadataName | Incremental cookbook | FAIL | Yes (High) |
| Use records for models | Incremental cookbook | FAIL | Yes (High) |
| Implement collection equality | Incremental cookbook | FAIL | Yes (High) |
| Don't store ISymbol/SyntaxNode | Incremental cookbook | PASS | No |
| Use StringBuilder for codegen | Incremental cookbook | PASS | No |
| Report diagnostics properly | Main cookbook | PASS | No |
| Avoid duplicate pipeline work | Incremental cookbook | FAIL | Yes (Medium) |
| Respect CancellationToken | Main cookbook | PARTIAL | Optional |
| Use .g.cs file suffix | Main cookbook | PASS | No |
| Additive-only generation | Main cookbook | PASS | No |
| No language feature emulation | Main cookbook | PASS | No |

---

## Conclusion

The source generator implementation demonstrates solid understanding of Roslyn generator fundamentals—correct interface usage, proper diagnostic reporting, and appropriate code generation patterns. However, critical performance optimizations are missing that could cause significant IDE lag in production environments.

The three high-priority fixes (ForAttributeWithMetadataName, record models, and EquatableArray) should be implemented before the generator is used in large codebases. These changes will enable proper incremental caching, reducing regeneration from "every keystroke" to "only when relevant code changes."
