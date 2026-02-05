# Source Generator for Workflow Executors: Rationale and Impact

## Overview

The Microsoft Agents AI Workflows framework has introduced a Roslyn source generator (`Microsoft.Agents.AI.Workflows.Generators`) that replaces the previous reflection-based approach for discovering and registering message handlers. This document explains why this change was made, what benefits it provides, and how it impacts framework users.

## Why Move from Reflection to Code Generation?

### The Previous Approach: `ReflectingExecutor<T>`

Previously, executors that needed automatic handler discovery inherited from `ReflectingExecutor<T>` and implemented marker interfaces like `IMessageHandler<TMessage>`:

```csharp
// Old approach - reflection-based
public class MyExecutor : ReflectingExecutor<MyExecutor>,
    IMessageHandler<QueryMessage>,
    IMessageHandler<CommandMessage, CommandResult>
{
    public ValueTask HandleAsync(QueryMessage msg, IWorkflowContext ctx, CancellationToken ct)
    {
        // Handle query
    }

    public ValueTask<CommandResult> HandleAsync(CommandMessage msg, IWorkflowContext ctx, CancellationToken ct)
    {
        // Handle command and return result
    }
}
```

This approach had several limitations:

1. **Runtime overhead**: Handler discovery happened at runtime via reflection, adding latency to executor initialization
2. **No AOT compatibility**: Reflection-based discovery doesn't work with Native AOT compilation
3. **Redundant declarations**: The interface list duplicated information already present in method signatures
4. **Limited metadata**: No clean way to declare yield/send types for protocol validation
5. **Hidden errors**: Invalid handler signatures weren't caught until runtime

### The New Approach: `[MessageHandler]` Attribute

The source generator enables a cleaner, attribute-based pattern:

```csharp
// New approach - source generated
[SendsMessage(typeof(PollToken))]
public partial class MyExecutor : Executor
{
    [MessageHandler]
    private ValueTask HandleQueryAsync(QueryMessage msg, IWorkflowContext ctx, CancellationToken ct)
    {
        // Handle query
    }

    [MessageHandler(Yield = [typeof(StreamChunk)], Send = [typeof(InternalMessage)])]
    private ValueTask<CommandResult> HandleCommandAsync(CommandMessage msg, IWorkflowContext ctx, CancellationToken ct)
    {
        // Handle command and return result
    }
}
```

The generator produces a partial class with `ConfigureRoutes()`, `ConfigureSentTypes()`, and `ConfigureYieldTypes()` implementations at compile time.

## What's Better About Code Generation?

### 1. Compile-Time Validation

Invalid handler signatures are caught during compilation, not at runtime:

```csharp
[MessageHandler]
private void InvalidHandler(string msg)  // Error WFGEN005: Missing IWorkflowContext parameter
{
}
```

Diagnostic errors include:
- `WFGEN001`: Handler missing `IWorkflowContext` parameter
- `WFGEN002`: Invalid return type (must be `void`, `ValueTask`, or `ValueTask<T>`)
- `WFGEN003`: Executor class must be `partial`
- `WFGEN004`: `[MessageHandler]` on non-Executor class
- `WFGEN005`: Insufficient parameters
- `WFGEN006`: `ConfigureRoutes` already manually defined

### 2. Zero Runtime Reflection

All handler registration happens at compile time. The generated code is simple, direct method calls:

```csharp
// Generated code
protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
{
    return routeBuilder
        .AddHandler<QueryMessage>(this.HandleQueryAsync)
        .AddHandler<CommandMessage, CommandResult>(this.HandleCommandAsync);
}
```

This eliminates:
- Reflection overhead during initialization
- Assembly scanning
- Dynamic delegate creation

### 3. Native AOT Compatibility

Because there's no runtime reflection, executors work seamlessly with .NET Native AOT compilation. This enables:
- Faster startup times
- Smaller deployment sizes
- Deployment to environments that don't support JIT compilation

### 4. Explicit Protocol Metadata

The `Yield` and `Send` properties on `[MessageHandler]` plus class-level `[SendsMessage]` and `[YieldsMessage]` attributes provide explicit protocol documentation:

```csharp
[SendsMessage(typeof(PollToken))]        // This executor sends PollToken messages
[YieldsMessage(typeof(FinalResult))]     // This executor yields FinalResult to workflow output
public partial class MyExecutor : Executor
{
    [MessageHandler(
        Yield = [typeof(StreamChunk)],    // This handler yields StreamChunk
        Send = [typeof(InternalQuery)])]  // This handler sends InternalQuery
    private ValueTask HandleAsync(Request req, IWorkflowContext ctx) { ... }
}
```

This metadata enables:
- Static protocol validation
- Better IDE tooling and documentation
- Clearer code intent

### 5. Handler Accessibility Freedom

Handlers can be `private`, `protected`, `internal`, or `public`. The old interface-based approach required public methods. Now you can encapsulate handler implementations:

```csharp
public partial class MyExecutor : Executor
{
    [MessageHandler]
    private ValueTask HandleInternalAsync(InternalMessage msg, IWorkflowContext ctx)
    {
        // Private handler - implementation detail
    }
}
```

### 6. Cleaner Inheritance

The generator properly handles inheritance chains, calling `base.ConfigureRoutes()` when appropriate:

```csharp
public partial class DerivedExecutor : BaseExecutor
{
    [MessageHandler]
    private ValueTask HandleDerivedAsync(DerivedMessage msg, IWorkflowContext ctx) { ... }
}

// Generated:
protected override RouteBuilder ConfigureRoutes(RouteBuilder routeBuilder)
{
    routeBuilder = base.ConfigureRoutes(routeBuilder);  // Preserves base handlers
    return routeBuilder
        .AddHandler<DerivedMessage>(this.HandleDerivedAsync);
}
```

## New Capabilities Enabled

### 1. Static Workflow Analysis

With explicit yield/send metadata, tools can analyze workflow graphs at compile time:
- Validate that all message types have handlers
- Detect unreachable executors
- Generate workflow documentation

### 2. Trimming-Safe Deployments

The generated code contains no reflection, making it fully compatible with IL trimming. This reduces deployment size significantly for serverless and edge scenarios.

### 3. Better IDE Experience

Because the generator runs in the IDE, you get:
- Immediate feedback on handler signature errors
- IntelliSense for generated methods
- Go-to-definition on generated code

### 4. Protocol Documentation Generation

The explicit type metadata can be used to generate:
- API documentation
- OpenAPI/Swagger specs for workflow endpoints
- Visual workflow diagrams

## Impact on Framework Users

### Migration Path

Existing code using `ReflectingExecutor<T>` continues to work but is marked `[Obsolete]`. To migrate:

1. Change base class from `ReflectingExecutor<T>` to `Executor`
2. Add `partial` modifier to the class
3. Replace `IMessageHandler<T>` interfaces with `[MessageHandler]` attributes
4. Optionally add `Yield`/`Send` metadata for protocol validation

**Before:**
```csharp
public class MyExecutor : ReflectingExecutor<MyExecutor>, IMessageHandler<Query, Result>
{
    public ValueTask<Result> HandleAsync(Query q, IWorkflowContext ctx, CancellationToken ct) { ... }
}
```

**After:**
```csharp
public partial class MyExecutor : Executor
{
    [MessageHandler]
    private ValueTask<Result> HandleQueryAsync(Query q, IWorkflowContext ctx, CancellationToken ct) { ... }
}
```

### Breaking Changes

- Classes using `[MessageHandler]` **must** be `partial`
- Handler methods must have at least 2 parameters: `(TMessage, IWorkflowContext)`
- Return type must be `void`, `ValueTask`, or `ValueTask<T>`

### Performance Improvements

Users can expect:
- **Faster executor initialization**: No reflection overhead
- **Reduced memory allocation**: No dynamic delegate creation
- **AOT deployment support**: Full Native AOT compatibility
- **Smaller trimmed deployments**: No reflection metadata preserved

### NuGet Package

The generator is distributed as a separate NuGet package (`Microsoft.Agents.AI.Workflows.Generators`) that's automatically referenced by the main Workflows package. It's packaged as an analyzer, so it:
- Runs automatically during build
- Requires no additional configuration
- Works in all IDEs that support Roslyn analyzers

## Summary

The move from reflection to source generation represents a significant improvement in the Workflows framework:

| Aspect | Reflection (Old) | Source Generator (New) |
|--------|------------------|------------------------|
| Handler discovery | Runtime | Compile-time |
| Error detection | Runtime exceptions | Compiler errors |
| AOT support | No | Yes |
| Trimming support | Limited | Full |
| Protocol metadata | Implicit | Explicit |
| Handler visibility | Public only | Any |
| Initialization speed | Slower | Faster |

The source generator approach aligns with modern .NET best practices and positions the framework for future scenarios including edge computing, serverless, and mobile deployments where AOT compilation and minimal footprint are essential.
