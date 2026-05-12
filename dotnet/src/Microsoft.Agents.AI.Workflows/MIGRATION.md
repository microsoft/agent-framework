# Migration Guide: ReflectingExecutor to [MessageHandler] Attributes

## Overview

The `ReflectingExecutor<T>` base class is obsolete and will be removed in a future version. The replacement is the `[MessageHandler]` attribute pattern with a `partial` class deriving from `Executor`. This approach uses a Roslyn source generator to produce handler registrations at compile time, eliminating reflection overhead and enabling compile-time diagnostics for configuration errors.

## Step-by-Step Conversion

### Step 1: Change the base class

Replace `ReflectingExecutor<TActual>` with `Executor` (or `Executor<TInput>` / `Executor<TInput, TOutput>` for typed executors).

```csharp
// Before
public class MyExecutor : ReflectingExecutor<MyExecutor>

// After
public partial class MyExecutor : Executor
```

### Step 2: Add the `partial` modifier

The source generator requires the class to be declared as `partial`. Add this modifier to every declaration of the class.

### Step 3: Remove `IMessageHandler<T>` interface implementations

The `[MessageHandler]` attribute replaces the `IMessageHandler<T>` and `IMessageHandler<T, TResult>` interfaces. Remove all `IMessageHandler<>` implementations from the class.

### Step 4: Add `[MessageHandler]` attribute to handler methods

Mark each handler method with `[MessageHandler]`. The method signature determines the input type and optional output type.

```csharp
// Before (interface-based)
public class MyExecutor : ReflectingExecutor<MyExecutor>, IMessageHandler<MyQuery, MyResponse>
{
    public async ValueTask<MyResponse> HandleAsync(MyQuery query, IWorkflowContext ctx, CancellationToken ct)
    {
        return new MyResponse();
    }
}

// After (attribute-based)
public partial class MyExecutor : Executor
{
    [MessageHandler]
    private async ValueTask<MyResponse> HandleQueryAsync(MyQuery query, IWorkflowContext ctx, CancellationToken ct)
    {
        return new MyResponse();
    }
}
```

### Step 5: Preserve class-level attributes

`[SendsMessage]` and `[YieldsOutput]` class-level attributes work the same way in both patterns. No changes needed.

### Step 6: Remove manual ConfigureProtocol override

The source generator produces the `ConfigureProtocol` override automatically. Remove any manual override unless you need custom behavior beyond what the attributes express. If you keep a manual override, the generator will emit diagnostic MAFGENWF006 and skip code generation for that class.

## Auto-Yield and Auto-Send Behavior

`ExecutorOptions` controls two automatic behaviors:

- **`AutoSendMessageHandlerResultObject`** (default: `true`): When a handler returns a value, that return type is automatically registered as a "sent message" type.
- **`AutoYieldOutputHandlerResultObject`** (default: `true`): When a handler returns a value, that return type is automatically registered as a "yielded output" type.

These defaults mean handler return values are automatically added to the protocol's send and yield type sets. To opt out, set the relevant option to `false` in your constructor:

```csharp
public MyExecutor() : base("my-executor", new ExecutorOptions
{
    AutoSendMessageHandlerResultObject = false,
    AutoYieldOutputHandlerResultObject = false
})
{ }
```

Note that specialized base classes may override these defaults. For example, `ChatProtocolExecutor` sets `AutoSendMessageHandlerResultObject = false`.

## Naming Differences

The implementation uses names that align with the fluent API rather than the original design plan:

- `YieldsOutputAttribute` (not `YieldsMessageAttribute`) — matches `ProtocolBuilder.YieldsOutput<T>()`
- `ConfigureProtocol` (not `ConfigureRoutes`) — matches the actual method name on `Executor`
- Diagnostic IDs use the `MAFGENWF` prefix (e.g., MAFGENWF001-010)

## Known Limitations

- **Partial class required**: The containing class must be declared as `partial`. The generator emits MAFGENWF003 if it is not.
- **Method-level `[SendsMessage]`/`[YieldsOutput]` on non-handler methods**: These attributes are silently ignored when applied to methods that are not marked with `[MessageHandler]`.
- **Maximum 3 parameters**: Handler methods accept at most 3 parameters (message, `IWorkflowContext`, optional `CancellationToken`). The generator emits MAFGENWF009 for methods exceeding this limit.
- **One handler per input type**: Only one `[MessageHandler]` method per input type is allowed per class. Duplicates produce MAFGENWF008.
