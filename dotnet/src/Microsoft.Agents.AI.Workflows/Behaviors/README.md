# Pipeline Behaviors

Pipeline behaviors provide extension points for adding cross-cutting concerns to workflow and executor execution. They enable developers to inject custom logic before and after workflow operations without modifying core workflow code.

## Overview

The pipeline behavior system supports two levels of extensibility:

- **Workflow Behaviors** - Execute logic when workflows start and end
- **Executor Behaviors** - Execute logic when executors process messages

Multiple behaviors can be chained together, forming a pipeline where each behavior wraps the next, similar to middleware in ASP.NET Core.

## Key Features

- ✅ **Chain of Responsibility Pattern** - Multiple behaviors execute in order
- ✅ **Zero Overhead** - Fast path when no behaviors are registered
- ✅ **Type-Safe Context** - Full access to execution information
- ✅ **Exception Wrapping** - Behaviors wrapped with `BehaviorExecutionException`
- ✅ **Async/Await Support** - Full async execution throughout the pipeline
- ✅ **Short-Circuit Capability** - Behaviors can prevent downstream execution

## Architecture

### Execution Flow

```
Workflow Start
    ├─> WorkflowBehavior 1 (Starting)      // entered in registration order
    ├─> WorkflowBehavior 2 (Starting)
    │
    ├─> SuperStep Loop
    │   └─> Executor Message Processing
    │       ├─> ExecutorBehavior 1         // code before `await continuation()`
    │       ├─> ExecutorBehavior 2
    │       ├─> Actual Handler Execution
    │       ├─> ExecutorBehavior 2         // code after `await continuation()`
    │       └─> ExecutorBehavior 1
    │
    ├─> WorkflowBehavior 1 (Ending)        // a separate pipeline pass, also
    └─> WorkflowBehavior 2 (Ending)        // entered in registration order
```

Executor behaviors form a single nested chain around the handler, so the first-registered behavior is
the outermost one: it runs first on the way in and last on the way out. The `Starting` and `Ending`
workflow stages are two *independent* pipeline passes — `Ending` is not an unwinding of `Starting`,
so both are entered in registration order.

### Pipeline Behavior Interfaces

#### IExecutorBehavior

Wraps individual executor step execution:

```csharp
public interface IExecutorBehavior
{
    ValueTask<object?> HandleAsync(
        ExecutorBehaviorContext context,
        ExecutorBehaviorContinuation continuation,
        CancellationToken cancellationToken = default);
}
```

**Context Properties:**
- `ExecutorId` - Unique identifier of the executor
- `ExecutorType` - Type of the executor being invoked
- `Message` - The message being processed
- `MessageType` - Type of the message
- `RunId` - Unique workflow run identifier
- `Stage` - Execution stage. Currently only `PreExecution`: the behavior is invoked once per executor
  call, before the executor begins processing the message. To run logic after the executor completes,
  place it after the `await continuation()` call rather than looking for a separate post-execution stage.
- `WorkflowContext` - Access to workflow operations
- `TraceContext` - Distributed tracing information
- `Properties` - Mutable `IDictionary<string, object>`, initialized empty by the framework, for passing
  data between behaviors. A fresh instance is created per executor invocation, so values written by an
  outer behavior are visible to inner behaviors and to code after `await continuation()` in the same
  call, but do not flow to later invocations. Not thread-safe.

#### IWorkflowBehavior

Wraps workflow-level execution:

```csharp
public interface IWorkflowBehavior
{
    ValueTask<TResult> HandleAsync<TResult>(
        WorkflowBehaviorContext context,
        WorkflowBehaviorContinuation<TResult> continuation,
        CancellationToken cancellationToken = default);
}
```

**Context Properties:**
- `WorkflowName` - Name of the workflow
- `WorkflowDescription` - Optional description
- `RunId` - Unique workflow run identifier
- `StartExecutorId` - ID of the starting executor
- `Stage` - Workflow execution stage:
  - `Starting` - The workflow is beginning execution
  - `Ending` - The workflow is completing execution
- `Properties` - Mutable `IDictionary<string, object>`, initialized empty by the framework, for passing
  data between behaviors within a single stage. `Starting` and `Ending` each get their own instance, so
  values do not carry across stages. Not thread-safe.

## Usage Examples

### Example 1: Logging Behavior

```csharp
public class LoggingExecutorBehavior : IExecutorBehavior
{
    private readonly ILogger<LoggingExecutorBehavior> _logger;

    public LoggingExecutorBehavior(ILogger<LoggingExecutorBehavior> logger)
    {
        _logger = logger;
    }

    public async ValueTask<object?> HandleAsync(
        ExecutorBehaviorContext context,
        ExecutorBehaviorContinuation continuation,
        CancellationToken cancellationToken)
    {
        _logger.LogInformation(
            "Executing {ExecutorId} with message type {MessageType}",
            context.ExecutorId,
            context.MessageType.Name);

        var stopwatch = Stopwatch.StartNew();

        try
        {
            var result = await continuation(cancellationToken);

            _logger.LogInformation(
                "Completed {ExecutorId} in {ElapsedMs}ms",
                context.ExecutorId,
                stopwatch.ElapsedMilliseconds);

            return result;
        }
        catch (Exception ex)
        {
            _logger.LogError(
                ex,
                "Failed {ExecutorId} after {ElapsedMs}ms",
                context.ExecutorId,
                stopwatch.ElapsedMilliseconds);

            throw;
        }
    }
}
```

### Example 2: Validation Behavior

```csharp
public class ValidationBehavior : IExecutorBehavior
{
    public async ValueTask<object?> HandleAsync(
        ExecutorBehaviorContext context,
        ExecutorBehaviorContinuation continuation,
        CancellationToken cancellationToken)
    {
        // Pre-execution validation
        if (context.Message is IValidatable validatable)
        {
            var validationResult = validatable.Validate();
            if (!validationResult.IsValid)
            {
                throw new ValidationException(
                    $"Message validation failed for {context.MessageType.Name}: " +
                    string.Join(", ", validationResult.Errors));
            }
        }

        // Continue pipeline
        return await continuation(cancellationToken);
    }
}
```

### Example 3: Workflow Telemetry Behavior

```csharp
public class WorkflowTelemetryBehavior : IWorkflowBehavior
{
    private readonly IMetrics _metrics;

    public WorkflowTelemetryBehavior(IMetrics metrics)
    {
        _metrics = metrics;
    }

    public async ValueTask<TResult> HandleAsync<TResult>(
        WorkflowBehaviorContext context,
        WorkflowBehaviorContinuation<TResult> continuation,
        CancellationToken cancellationToken)
    {
        if (context.Stage == WorkflowStage.Starting)
        {
            _metrics.IncrementCounter("workflow.starts", 1,
                new[] { new KeyValuePair<string, object?>("workflow", context.WorkflowName) });
        }

        var result = await continuation(cancellationToken);

        if (context.Stage == WorkflowStage.Ending)
        {
            _metrics.IncrementCounter("workflow.completions", 1,
                new[] { new KeyValuePair<string, object?>("workflow", context.WorkflowName) });
        }

        return result;
    }
}
```

### Example 4: Retry Behavior

```csharp
public class RetryBehavior : IExecutorBehavior
{
    private readonly int _maxRetries;
    private readonly TimeSpan _retryDelay;

    public RetryBehavior(int maxRetries = 3, TimeSpan? retryDelay = null)
    {
        _maxRetries = maxRetries;
        _retryDelay = retryDelay ?? TimeSpan.FromMilliseconds(100);
    }

    public async ValueTask<object?> HandleAsync(
        ExecutorBehaviorContext context,
        ExecutorBehaviorContinuation continuation,
        CancellationToken cancellationToken)
    {
        for (int attempt = 1; attempt <= _maxRetries; attempt++)
        {
            try
            {
                return await continuation(cancellationToken);
            }
            catch (Exception) when (attempt < _maxRetries)
            {
                // Wait before retrying
                await Task.Delay(_retryDelay, cancellationToken);
            }
        }

        // Final attempt without catching
        return await continuation(cancellationToken);
    }
}
```

## Registration

Register behaviors using the `WithBehaviors` method on `WorkflowBuilder`:

```csharp
var workflow = new WorkflowBuilder(startExecutor)
    .WithBehaviors(options =>
    {
        // Add executor behaviors (execute for each executor step)
        options.AddExecutorBehavior(new LoggingExecutorBehavior(logger));
        options.AddExecutorBehavior(new ValidationBehavior());
        options.AddExecutorBehavior(new RetryBehavior(maxRetries: 3));

        // Add workflow behaviors (execute at workflow start/end)
        options.AddWorkflowBehavior(new WorkflowTelemetryBehavior(metrics));
    })
    .AddEdge(startExecutor, nextExecutor)
    .Build();
```

### Registration with Factory Methods

For behaviors with parameterless constructors:

```csharp
.WithBehaviors(options =>
{
    options.AddExecutorBehavior<SimpleLoggingBehavior>();
    options.AddWorkflowBehavior<SimpleTelemetryBehavior>();
})
```

## Execution Order

Behaviors execute in the order they are registered:

```csharp
options.AddExecutorBehavior(new Behavior1()); // Outer wrapper
options.AddExecutorBehavior(new Behavior2()); // Middle wrapper
options.AddExecutorBehavior(new Behavior3()); // Inner wrapper (closest to handler)
```

**Execution Flow:**
1. Behavior1.HandleAsync (before)
2. Behavior2.HandleAsync (before)
3. Behavior3.HandleAsync (before)
4. **Actual Handler Execution**
5. Behavior3.HandleAsync (after)
6. Behavior2.HandleAsync (after)
7. Behavior1.HandleAsync (after)

## Error Handling

All behavior exceptions are automatically wrapped in `BehaviorExecutionException`:

```csharp
try
{
    // Execute workflow
}
catch (BehaviorExecutionException ex)
{
    Console.WriteLine($"Behavior {ex.BehaviorType} failed at {ex.Stage}");
    Console.WriteLine($"Inner exception: {ex.InnerException?.Message}");
}
```

**Properties:**
- `BehaviorType` - Full type name of the failed behavior
- `Stage` - Execution stage when failure occurred
- `InnerException` - Original exception thrown by the behavior

## Performance Considerations

### Zero Overhead When Disabled

When no behaviors are registered, the pipeline has zero overhead:

```csharp
if (_executorBehaviors.Count == 0)
{
    return await finalHandler(cancellationToken); // Direct execution
}
```

### Minimal Allocation

- Behaviors are stored as `List<T>` for optimal iteration
- Delegate chain built once per execution
- No allocations in the fast path

## Common Use Cases

### 1. **Logging and Diagnostics**
```csharp
- Log executor execution with timing
- Track message types and payloads
- Record workflow lifecycle events
```

### 2. **Telemetry and Metrics**
```csharp
- Count workflow starts/completions
- Measure executor execution time
- Track message processing rates
```

### 3. **Validation**
```csharp
- Validate messages before execution
- Enforce business rules
- Check preconditions
```

### 4. **Resilience**
```csharp
- Implement retry logic
- Add circuit breakers
- Handle transient failures
```

### 5. **Security**
```csharp
- Authorization checks
- Audit logging
- Sensitive data masking
```

### 6. **Distributed Tracing**
```csharp
- Create OpenTelemetry spans
- Propagate trace context
- Add custom span attributes
```

## Best Practices

### ✅ Do

- **Keep behaviors focused** - One concern per behavior
- **Handle cancellation** - Respect `CancellationToken`
- **Use dependency injection** - Pass dependencies via constructor
- **Document side effects** - Be clear about what behaviors do
- **Test behaviors independently** - Unit test each behavior in isolation

### ❌ Don't

- **Modify message content** - Behaviors should observe, not mutate
- **Catch all exceptions** - Let exceptions propagate (they'll be wrapped)
- **Block threads** - Always use async/await
- **Share state** - Behaviors should be stateless or thread-safe
- **Assume execution order** - Each behavior should work independently

## Thread Safety

Behavior instances may be called concurrently when:
- Multiple workflows execute simultaneously
- The same workflow processes multiple messages in parallel

**Ensure behaviors are thread-safe:**
- Use immutable state
- Synchronize mutable state access
- Avoid shared static fields

## Advanced Patterns

### Conditional Execution

```csharp
public async ValueTask<object?> HandleAsync(
    ExecutorBehaviorContext context,
    ExecutorBehaviorContinuation continuation,
    CancellationToken cancellationToken)
{
    // Only apply to specific executor types
    if (context.ExecutorType == typeof(CriticalExecutor))
    {
        // Apply special handling
    }

    return await continuation(cancellationToken);
}
```

### Short-Circuiting

```csharp
public async ValueTask<object?> HandleAsync(
    ExecutorBehaviorContext context,
    ExecutorBehaviorContinuation continuation,
    CancellationToken cancellationToken)
{
    // Check cache
    if (_cache.TryGet(context.Message, out var cachedResult))
    {
        return cachedResult; // Skip execution
    }

    var result = await continuation(cancellationToken);
    _cache.Set(context.Message, result);
    return result;
}
```

### Context Enrichment

```csharp
public async ValueTask<object?> HandleAsync(
    ExecutorBehaviorContext context,
    ExecutorBehaviorContinuation continuation,
    CancellationToken cancellationToken)
{
    // Add custom trace attributes
    Activity.Current?.SetTag("executor.id", context.ExecutorId);
    Activity.Current?.SetTag("message.type", context.MessageType.Name);

    return await continuation(cancellationToken);
}
```

## Backward Compatibility

Pipeline behaviors are completely opt-in:
- Existing workflows work without modification
- No performance impact when behaviors aren't registered
- New functionality doesn't break existing code

## API Reference

### Core Types

- `IWorkflowBehavior` - Workflow-level behavior interface
- `IExecutorBehavior` - Executor-level behavior interface
- `WorkflowBehaviorContext` - Context for workflow behaviors
- `ExecutorBehaviorContext` - Context for executor behaviors
- `WorkflowBehaviorOptions` - Registration API
- `BehaviorExecutionException` - Exception wrapper

### Enums

- `WorkflowStage` - Starting, Ending
- `ExecutorStage` - PreExecution

### Extension Methods

- `WorkflowBuilder.WithBehaviors(Action<WorkflowBehaviorOptions>)` - Register behaviors
