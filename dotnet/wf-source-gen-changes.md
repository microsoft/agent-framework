# Workflow Executor Route Source Generator - Implementation Summary

This document summarizes all changes made to implement a Roslyn source generator that replaces the reflection-based `ReflectingExecutor<T>` pattern with compile-time code generation using `[MessageHandler]` attributes.

## Overview

The source generator automatically discovers methods marked with `[MessageHandler]` and generates `ConfigureRoutes`, `ConfigureSentTypes`, and `ConfigureYieldTypes` method implementations at compile time. This improves AOT compatibility and eliminates the need for the CRTP (Curiously Recurring Template Pattern) used by `ReflectingExecutor<T>`.

## New Files Created

### Attributes (3 files)

| File | Purpose |
|------|---------|
| `src/Microsoft.Agents.AI.Workflows/Attributes/MessageHandlerAttribute.cs` | Marks methods as message handlers with optional `Yield` and `Send` type arrays |
| `src/Microsoft.Agents.AI.Workflows/Attributes/SendsMessageAttribute.cs` | Class-level attribute declaring message types an executor may send |
| `src/Microsoft.Agents.AI.Workflows/Attributes/YieldsMessageAttribute.cs` | Class-level attribute declaring output types an executor may yield |

### Source Generator Project (8 files)

| File | Purpose |
|------|---------|
| `src/Microsoft.Agents.AI.Workflows.Generators/Microsoft.Agents.AI.Workflows.Generators.csproj` | Project file targeting netstandard2.0 with Roslyn component settings |
| `src/Microsoft.Agents.AI.Workflows.Generators/ExecutorRouteGenerator.cs` | Main incremental generator implementing `IIncrementalGenerator` |
| `src/Microsoft.Agents.AI.Workflows.Generators/Models/HandlerInfo.cs` | Data model for handler method information |
| `src/Microsoft.Agents.AI.Workflows.Generators/Models/ExecutorInfo.cs` | Data model for executor class information |
| `src/Microsoft.Agents.AI.Workflows.Generators/Analysis/SyntaxDetector.cs` | Fast syntax-level candidate detection |
| `src/Microsoft.Agents.AI.Workflows.Generators/Analysis/SemanticAnalyzer.cs` | Semantic validation and type extraction |
| `src/Microsoft.Agents.AI.Workflows.Generators/Generation/SourceBuilder.cs` | Code generation logic |
| `src/Microsoft.Agents.AI.Workflows.Generators/Diagnostics/DiagnosticDescriptors.cs` | Analyzer diagnostic definitions |

## Files Modified

### Project Files

| File | Changes |
|------|---------|
| `src/Microsoft.Agents.AI.Workflows/Microsoft.Agents.AI.Workflows.csproj` | Added generator project reference and `InternalsVisibleTo` for generator tests |
| `Directory.Packages.props` | Added `Microsoft.CodeAnalysis.Analyzers` version 3.11.0 |
| `agent-framework-dotnet.slnx` | Added generator project to solution |

### Obsolete Annotations

| File | Changes |
|------|---------|
| `src/Microsoft.Agents.AI.Workflows/Reflection/ReflectingExecutor.cs` | Added `[Obsolete]` attribute with migration guidance |
| `src/Microsoft.Agents.AI.Workflows/Reflection/IMessageHandler.cs` | Added `[Obsolete]` to both `IMessageHandler<T>` and `IMessageHandler<T,TResult>` interfaces |

### Pragma Suppressions for Internal Obsolete Usage

| File | Changes |
|------|---------|
| `src/Microsoft.Agents.AI.Workflows/Executor.cs` | Added `#pragma warning disable CS0618` |
| `src/Microsoft.Agents.AI.Workflows/StatefulExecutor.cs` | Added `#pragma warning disable CS0618` |
| `src/Microsoft.Agents.AI.Workflows/Reflection/RouteBuilderExtensions.cs` | Added `#pragma warning disable CS0618` |
| `src/Microsoft.Agents.AI.Workflows/Reflection/MessageHandlerInfo.cs` | Added `#pragma warning disable CS0618` |

### Test File Pragma Suppressions

| File | Changes |
|------|---------|
| `tests/Microsoft.Agents.AI.Workflows.UnitTests/Sample/01_Simple_Workflow_Sequential.cs` | Added `#pragma warning disable CS0618` for legacy pattern testing |
| `tests/Microsoft.Agents.AI.Workflows.UnitTests/Sample/02_Simple_Workflow_Condition.cs` | Added `#pragma warning disable CS0618` for legacy pattern testing |
| `tests/Microsoft.Agents.AI.Workflows.UnitTests/Sample/03_Simple_Workflow_Loop.cs` | Added `#pragma warning disable CS0618` for legacy pattern testing |
| `tests/Microsoft.Agents.AI.Workflows.UnitTests/ReflectionSmokeTest.cs` | Added `#pragma warning disable CS0618` for legacy pattern testing |

## Attribute Definitions

### MessageHandlerAttribute

```csharp
[AttributeUsage(AttributeTargets.Method, AllowMultiple = false, Inherited = false)]
public sealed class MessageHandlerAttribute : Attribute
{
    public Type[]? Yield { get; set; }  // Types yielded as workflow outputs
    public Type[]? Send { get; set; }   // Types sent to other executors
}
```

### SendsMessageAttribute

```csharp
[AttributeUsage(AttributeTargets.Class, AllowMultiple = true, Inherited = true)]
public sealed class SendsMessageAttribute : Attribute
{
    public Type Type { get; }
    public SendsMessageAttribute(Type type) => this.Type = Throw.IfNull(type);
}
```

### YieldsMessageAttribute

```csharp
[AttributeUsage(AttributeTargets.Class, AllowMultiple = true, Inherited = true)]
public sealed class YieldsMessageAttribute : Attribute
{
    public Type Type { get; }
    public YieldsMessageAttribute(Type type) => this.Type = Throw.IfNull(type);
}
```

## Diagnostic Rules

| ID | Severity | Description |
|----|----------|-------------|
| `WFGEN001` | Error | Handler method must have at least 2 parameters (message and IWorkflowContext) |
| `WFGEN002` | Error | Handler method's second parameter must be IWorkflowContext |
| `WFGEN003` | Error | Handler method must return void, ValueTask, or ValueTask<T> |
| `WFGEN004` | Error | Executor class with [MessageHandler] methods must be declared as partial |
| `WFGEN005` | Warning | [MessageHandler] attribute on method in non-Executor class (ignored) |
| `WFGEN006` | Info | ConfigureRoutes already defined manually, [MessageHandler] methods ignored |
| `WFGEN007` | Error | Handler method's third parameter (if present) must be CancellationToken |

## Handler Signature Support

The generator supports the following method signatures:

| Return Type | Parameters | Generated Call |
|-------------|------------|----------------|
| `void` | `(TMessage, IWorkflowContext)` | `AddHandler<TMessage>(this.Method)` |
| `void` | `(TMessage, IWorkflowContext, CancellationToken)` | `AddHandler<TMessage>(this.Method)` |
| `ValueTask` | `(TMessage, IWorkflowContext)` | `AddHandler<TMessage>(this.Method)` |
| `ValueTask` | `(TMessage, IWorkflowContext, CancellationToken)` | `AddHandler<TMessage>(this.Method)` |
| `TResult` | `(TMessage, IWorkflowContext)` | `AddHandler<TMessage, TResult>(this.Method)` |
| `TResult` | `(TMessage, IWorkflowContext, CancellationToken)` | `AddHandler<TMessage, TResult>(this.Method)` |
| `ValueTask<TResult>` | `(TMessage, IWorkflowContext)` | `AddHandler<TMessage, TResult>(this.Method)` |
| `ValueTask<TResult>` | `(TMessage, IWorkflowContext, CancellationToken)` | `AddHandler<TMessage, TResult>(this.Method)` |

## Generated Code Example

### Input (User Code)

```csharp
[SendsMessage(typeof(PollToken))]
public partial class MyChatExecutor : Executor
{
    [MessageHandler]
    private async ValueTask<ChatResponse> HandleQueryAsync(
        ChatQuery query, IWorkflowContext ctx, CancellationToken ct)
    {
        return new ChatResponse(...);
    }

    [MessageHandler(Yield = new[] { typeof(StreamChunk) }, Send = new[] { typeof(InternalMessage) })]
    private void HandleStream(StreamRequest req, IWorkflowContext ctx)
    {
        // Handler implementation
    }
}
```

### Output (Generated Code)

```csharp
// <auto-generated/>
#nullable enable

namespace MyNamespace;

partial class MyChatExecutor
{
    protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
    {
        return routeBuilder
            .AddHandler<ChatQuery, ChatResponse>(this.HandleQueryAsync)
            .AddHandler<StreamRequest>(this.HandleStream);
    }

    protected override ISet<Type> ConfigureSentTypes()
    {
        var types = base.ConfigureSentTypes();
        types.Add(typeof(PollToken));
        types.Add(typeof(InternalMessage));
        return types;
    }

    protected override ISet<Type> ConfigureYieldTypes()
    {
        var types = base.ConfigureYieldTypes();
        types.Add(typeof(ChatResponse));
        types.Add(typeof(StreamChunk));
        return types;
    }
}
```

## Build Issues Resolved

### 1. NU1008 - Central Package Management
Package references in the generator project had inline versions, which conflicts with central package management. Fixed by removing `Version` attributes from `PackageReference` items.

### 2. RS2008 - Analyzer Release Tracking
Roslyn requires analyzer release tracking documentation. Fixed by adding `<NoWarn>$(NoWarn);RS2008</NoWarn>` to the generator project.

### 3. CA1068 - CancellationToken Parameter Order
Method parameters were in wrong order. Fixed by reordering `CancellationToken` to be last.

### 4. RCS1146 - Conditional Access
Used null check with `&&` instead of `?.` operator. Fixed by using conditional access.

### 5. CA1310 - StringComparison
`StartsWith(string)` calls without `StringComparison`. Fixed by adding `StringComparison.Ordinal`.

### 6. CS0103 - Missing Using Directive
Missing `using System;` in SemanticAnalyzer.cs. Fixed by adding the using directive.

### 7. CS0618 - Obsolete Warnings as Errors
Internal uses of obsolete types caused build failures (TreatWarningsAsErrors). Fixed by adding `#pragma warning disable CS0618` to affected internal files and test files.

### 8. NU1109 - Package Version Conflict
`Microsoft.CodeAnalysis.Analyzers` 3.3.4 conflicts with `Microsoft.CodeAnalysis.CSharp` 4.14.0 which requires >= 3.11.0. Fixed by updating version to 3.11.0 in `Directory.Packages.props`.

### 9. RS1041 - Wrong Target Framework for Analyzer
The generator was being multi-targeted due to inherited `TargetFrameworks` from `Directory.Build.props`. Fixed by clearing `TargetFrameworks` and only setting `TargetFramework` to `netstandard2.0`.

## Migration Guide

### Before (Reflection-based)

```csharp
public class MyExecutor : ReflectingExecutor<MyExecutor>, IMessageHandler<MyMessage, MyResult>
{
    public MyExecutor() : base("MyExecutor") { }

    public ValueTask<MyResult> HandleAsync(MyMessage message, IWorkflowContext context, CancellationToken ct)
    {
        // Handler implementation
    }
}
```

### After (Source Generator)

```csharp
public partial class MyExecutor : Executor
{
    public MyExecutor() : base("MyExecutor") { }

    [MessageHandler]
    private ValueTask<MyResult> HandleAsync(MyMessage message, IWorkflowContext context, CancellationToken ct)
    {
        // Handler implementation
    }
}
```

Key migration steps:
1. Change base class from `ReflectingExecutor<T>` to `Executor`
2. Add `partial` modifier to the class
3. Remove `IMessageHandler<T>` interface implementations
4. Add `[MessageHandler]` attribute to handler methods
5. Handler methods can now be any accessibility (private, protected, internal, public)

## Future Work

- Create comprehensive unit tests for the source generator
- Add integration tests verifying generated routes match reflection-discovered routes
- Consider adding IDE quick-fix for migrating from `ReflectingExecutor<T>` pattern
