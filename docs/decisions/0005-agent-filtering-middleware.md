---
status: proposed
contact: rogerbarreto
date: 2025-08-22
deciders: markwallace-microsoft, rogerbarreto, westey-m, dmytrostruk, sergeymenshykh
informed: {}
---

# Agent Filtering Middleware Design

## Context and Problem Statement

The current Agent Framework lacks a standardized, extensible mechanism for intercepting and processing agent execution. Developers need the ability to add custom filters/middleware to intercept and modify agent behavior at various stages of the execution pipeline. While the framework has basic agent abstractions with `RunAsync` and `RunStreamingAsync` methods, and standards like approval workflows, there is no middleware that allows developers to intercept and modify agent behavior at different agent execution contexts.

The challenge is to design an architecture that supports:
- Multiple execution contexts (invocation, function calls, approval requests, error handling)
- Support for both streaming and non-streaming scenarios
- Dependency injection friendly setup

## Decision Drivers

- Agents should be able to intercept and modify agent behavior at various stages of the execution pipeline.
- The design should be simple and intuitive for developers to understand and use.
- The design should be extensible to support new execution contexts and scenarios.
- The design should support both manual and dependency injection configuration.
- The design should allow flexible custom behaviors provided by enough context information.
- The design should be exception friendly and allow clear error handling and recovery mechanisms.

## Considered Options

### Option 1: Semantic Kernel Approach

Similar to the Semantic Kernel kernel filters this option involves exposing different interface and properties for each specialized filter.

```csharp

var services = new ServiceCollection();
services.AddSingleton<IAgentRunFilter, MyAgentRunFilter>();
services.AddSingleton<IAgentFunctionCallFilter, MyAgentFunctionCallFilter>();

// Using DI
var agent = new MyAgent(services.BuildServiceProvider());

// Manual
var agent = new MyAgent();
agent.RunFilters.Add(new MyAgentRunFilter());
agent.FunctionCallFilters.Add(new MyAgentFunctionCallFilter());

public class MyAgentRunFilter : IAgentRunFilter
{
    public async Task<AgentRunContext> OnRunAsync(AgentRunContext context, Func<AgentRunContext, Task<AgentRunContext>> next, CancellationToken cancellationToken = default)
    {
        // Pre-run logic

        var result = await next(context);

        // Post-run logic

        return result;
    }
}

public interface IAgentRunFilter
{
    Task<AgentRunContext> OnRunAsync(AgentRunContext context, Func<AgentRunContext, Task<AgentRunContext>> next, CancellationToken cancellationToken = default);
}

public interface IAgentFunctionCallFilter
{
    Task<AgentFunctionCallContext> OnFunctionCallAsync(AgentFunctionCallContext context, Func<AgentFunctionCallContext, Task<AgentFunctionCallContext>> next, CancellationToken cancellationToken = default);
}

public class AIAgent
{
    private readonly AgentFilterProcessor _filterProcessor;

    public AIAgent(AgentFilterProcessor? filterProcessor = null)
    {
        _filterProcessor = filterProcessor ?? new AgentFilterProcessor();
    }

    public AIAgent(IServiceProvider serviceProvider)
    {
        _filterProcessor = serviceProvider.GetService<AgentFilterProcessor>() ?? new AgentFilterProcessor();

        // Auto-register filters from DI
        var filters = serviceProvider.GetServices<IAgentFilter>();
        foreach (var filter in filters)
        {
            _filterProcessor.AddFilter(filter);
        }
    }

    public async Task<AgentRunResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var context = new AgentRunContext(messages, thread, options);

        // Process through filter pipeline using the same pattern as Semantic Kernel
        var resultContext = await _filterProcessor.ProcessAsync(context, async ctx =>
        {
            // Core agent logic - implement actual agent execution here
            var response = await this.ExecuteCoreLogicAsync(ctx.Messages, ctx.Thread, ctx.Options, cancellationToken);
            return ctx.WithResponse(response);
        }, cancellationToken);

        // Extract the response from the context
        return resultContext.Response ?? throw new InvalidOperationException("Agent execution did not produce a response");
    }

    protected abstract Task<AgentRunResponse> ExecuteCoreLogicAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread,
        AgentRunOptions? options,
        CancellationToken cancellationToken);
}

```
#### Pros
- Clean separation of concerns
- Follows established patterns in Semantic Kernel and easy migration path
- No resistance or complaints from the community when used in Semantic Kernel

#### Cons
- Adding more filters may require adding more properties to the agent class.
- Filters are not always used, and adding this responsibility to the `AIAgent` abstraction level, may be an overkill.

### Option 2: Agent Filter Decorator Pattern

Similar to the `OpenTelemetryAgent` and the `DelegatingChatClient` in `Microsoft.Extensions.AI`, this option involves creating a `FilteredAgent` class that wraps agents and allows interception of method calls providing a collection of Filters to manage the wrapped agent.

```csharp
var services = new ServiceCollection();
services.AddSingleton<IAgentRunFilter, MyAgentRunFilter>();
services.AddSingleton<IAgentFunctionCallFilter, MyAgentFunctionCallFilter>();

// Using DI
var agent = new MyAgent();
var filteredAgent = new FilteringAIAgent(agent, services.BuildServiceProvider());

// Manual
var agent = new MyAgent();
var filteredAgent = new FilteringAIAgent(agent, 
    runFilters: [new MyAgentRunFilter()], 
    functionCallFilters: [new MyAgentFunctionCallFilter()]);

public class FilteringAIAgent
{
    private List<IAgentRunFilter>? _runFilters;
    private List<IAgentFunctionCallFilter>? _functionCallFilters;

    public FilteringAIAgent(AIAgent agent, IServiceProvider serviceProvider)
    {
        _innerAgent = agent;

        // Resolve filters from DI
        _runFilters ??= serviceProvider.GetServices<IAgentRunFilter>()?.ToList();
        _functionCallFilters ??= serviceProvider.GetServices<IAgentFunctionCallFilter>()?.ToList();
    }

    public async Task<AgentRunResponse> RunAsync(
        IReadOnlyCollection<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var context = new AgentRunContext(messages, thread, options);

        // Wrap core logic in filter pipeline
        var resultContext = await _runFilters.OnRunAsync(context, async ctx =>
        {
            // Core agent logic
            var response = await _innerAgent.RunAsync(ctx.Messages, ctx.Thread, ctx.Options, cancellationToken);
            return ctx.WithResponse(response);
        }, cancellationToken);

        // Extract the response from the context
        return resultContext.Response ?? throw new InvalidOperationException("Agent execution did not produce a response");
    }
}
```

#### Pros
- Clean separation of concerns
- Follows established patterns in `Microsoft.Extensions.AI`
- Non-intrusive to existing agent implementations
- Supports both manual and DI configuration
- Context-specific processing with self-registering filters
- Composable and reusable filter components

#### Cons
- Additional wrapper class adds complexity
- Requires explicit wrapping of agents
- Only viable for `ChatClientAgents` as other agents implementation will not have visibility/knowledge of the function call filters.

### Option 3: Dedicated Component for Filtering

This approach involves creating a dedicated `AgentFilterProcessor` that manages multiple collections of `IAgent_XYZ_Filter` instances.
Each agent can be provided with the processor or automatically have one injected from DI.

```csharp
var services = new ServiceCollection();
services.AddSingleton<IAgentRunFilter, MyAgentRunFilter>();
services.AddSingleton<IAgentFunctionCallFilter, MyAgentFunctionCallFilter>();
services.AddSingleton<AgentFilterProcessor>();

// Using DI
var provider = services.BuildServiceProvider();

// Filters are auto-registered with the processor from DI
var processor = provider.GetRequiredService<AgentFilterProcessor>();

// Manual
var processor = new AgentFilterProcessor();
processor.AddFilter(new MyAgentRunFilter());
processor.AddFilter(new MyAgentFunctionCallFilter());

// Agent takes processor in ctor or via DI
var agent = new MyAgent(processor);

```

The `AgentFilterProcessor` would manage the filter pipeline and chain execution using the same pattern as Semantic Kernel:

```csharp
public class AgentFilterProcessor
{
    private readonly List<IAgentFilter> _filters = new();

    public void AddFilter(IAgentFilter filter)
    {
        _filters.Add(filter);
    }

    public async Task<T> ProcessAsync<T>(T context, Func<T, Task<T>> coreLogic, CancellationToken cancellationToken = default)
        where T : AgentContext
    {
        // Get applicable filters for this context type
        var applicableFilters = _filters.Where(f => f.CanProcess(context)).ToList();

        // Start the filter chain execution
        return await this.InvokeFilterAsync(coreLogic, context, applicableFilters, cancellationToken);
    }

    /// <summary>
    /// This method will execute filters and core logic recursively using the Semantic Kernel pattern.
    /// If there are no registered filters, just core logic will be executed.
    /// If there are registered filters, filter at <paramref name="index"/> position will be executed.
    /// Second parameter of filter is callback. It can be either filter at <paramref name="index"/> + 1 position or core logic if there are no remaining filters to execute.
    /// Core logic will always be executed as last step after all filters.
    /// </summary>
    private async Task<T> InvokeFilterAsync<T>(
        Func<T, Task<T>> coreLogic,
        T context,
        IList<IAgentFilter> applicableFilters,
        CancellationToken cancellationToken,
        int index = 0) where T : AgentContext
    {
        if (applicableFilters is { Count: > 0 } && index < applicableFilters.Count)
        {
            // Execute the filter at the current index
            var result = await applicableFilters[index].OnProcessAsync(
                context,
                (ctx) => this.InvokeFilterAsync(coreLogic, (T)ctx, applicableFilters, cancellationToken, index + 1),
                cancellationToken
            ).ConfigureAwait(false);

            return (T)result;
        }
        else
        {
            // No more filters, execute core logic
            return await coreLogic(context).ConfigureAwait(false);
        }
    }
}
```

### Proposed Context Classes

The following context classes would be needed to support the filtering architecture:

```csharp
public abstract class AgentContext
{
    // For scenarios where the filter is processed by multiple agents sounds very desirable to provide access to the invoking agent
    public AIAgent Agent { get; } 

    public AgentRunOptions? Options { get; set; } // Options are allowed to be set by filters

    protected AgentContext(AIAgent agent, AgentRunOptions? options)
    {
        Agent = agent;
        Options = options;
    }
}

public class AgentRunContext : AgentContext
{
    public IList<ChatMessage> Messages { get; set; }

    public AgentThread? Thread { get; } 

    public AgentRunContext(AIAgent agent, IList<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options)
        : base(agent, options)
    {
        Messages = messages;
        Thread = thread;
    }
}

public class AgentFunctionInvocationContext : AgentContext
{
    // Similar to MEAI.FunctionInvocationContext
    public AIFunction Function { get; set; }
    public AIFunctionArguments Arguments { get; set; }
    public FunctionCallContent CallContent { get; set; }
    public IList<ChatMessage> Messages { get; set; }
    public ChatOptions? Options { get; set; }
    public int Iteration { get; set; }
    public int FunctionCallIndex { get; set; }
    public int FunctionCount { get; set; }
    public bool Terminate { get; set; }
    public bool IsStreaming { get; set; }
}

```

## Filter Middleware Design Options

### 1. Semantic Kernel Style

Has the benefit of clear separation of concerns, but this approach requires developers 
to manage and maintain separate collections for each filter type, increasing code complexity and maintenance overhead.

```csharp
// Use Case
var agent = new MyAgent();
agent.RunFilters.Add(new MyAgentRunFilter());
agent.RunFilters.Add(new MyMultipleFilterImplementation());
agent.FunctionCallFilters.Add(new MyAgentFunctionCallFilter());
agent.FunctionCallFilters.Add(new MyMultipleFilterImplementation());
agent.AYZFilters.Add(new MyAgentAYZFilter());
agent.AYZFilters.Add(new MyMultipleFilterImplementation());

// Impl
interface IAgentRunFilter
{
    Task<AgentRunContext> OnRunAsync(AgentRunContext context, Func<AgentRunContext, Task<AgentRunContext>> next, CancellationToken cancellationToken = default);
}
interface IAgentFunctionCallFilter
{
    Task<AgentFunctionCallContext> OnFunctionCallAsync(AgentFunctionCallContext context, Func<AgentFunctionCallContext, Task<AgentFunctionCallContext>> next, CancellationToken cancellationToken = default);
}
```

#### Pros
- Clean separation of concerns
- Follows established patterns in Semantic Kernel and easy migration path
- No resistance or complaints from the community when used in Semantic Kernel

#### Cons
- Adding more filters may require adding more properties to the agent/processor class.
- Adding more filters requires bigger code changes downstream to callers.

### 2. Generic Style

In a more generic approach, filters can be grouped in the same bucket and processed based on the context.
One generic interface for all filters, with context-specific implementations. 
Allow simple grouping of filters in the same list and adding new filter types with low code-changes.

```csharp
// Use Case
var agent = new MyAgent();
agent.Filters.Add(new MyAgentRunFilter());
agent.Filters.Add(new MyAgentFunctionCallFilter());
agent.Filters.Add(new MyAgentAYZFilter());
agent.Filters.Add(new MyMultipleFilterImplementation());

// Impl
interface IAgentFilter
{
    bool CanProcess(AgentContext context);
    Task<AgentContext> OnProcessAsync(AgentContext context, Func<AgentContext, Task<AgentContext>> next, CancellationToken cancellationToken = default);
}

interface IAgentFilter<T> : IAgentFilter where T : AgentContext
{
    Task<T> OnProcessAsync(T context, Func<T, Task<T>> next, CancellationToken cancellationToken = default);
}

class MySingleFilterImplementation : IAgentFilter<AgentRunContext>
{
    public bool CanProcess(AgentContext context)
        => context is AgentRunContext;

    public async Task<AgentContext> OnProcessAsync(AgentContext context, Func<AgentContext, Task<AgentContext>> next, CancellationToken cancellationToken = default)
    {
        Func<AgentRunContext, Task<AgentRunContext>> wrappedNext = async ctx => (AgentRunContext)await next(ctx);
        var result = await OnProcessAsync((AgentRunContext)context, wrappedNext, cancellationToken);
        return result;
    }

    public async Task<AgentRunContext> OnProcessAsync(AgentRunContext context, Func<AgentRunContext, Task<AgentRunContext>> next, CancellationToken cancellationToken = default)
    {
        // Pre-run logic
        var result = await next(context);
        // Post-run logic
        return result;
    }
}

class MyMultipleFilterImplementation : IAgentFilter<AgentRunContext>, IAgentFilter<FunctionCallAgentContext>
{
    public bool CanProcess(AgentContext context)
        => context is AgentRunContext or FunctionCallAgentContext;

    public async Task<AgentContext> OnProcessAsync(AgentContext context, Func<AgentContext, Task<AgentContext>> next, CancellationToken cancellationToken = default)
    {
        if (context is AgentRunContext runContext)
        {
            Func<AgentRunContext, Task<AgentRunContext>> wrappedNext = async ctx => (AgentRunContext)await next(ctx);
            return await OnProcessAsync(runContext, wrappedNext, cancellationToken);
        }

        if (context is FunctionCallAgentContext callContext)
        {
            Func<FunctionCallAgentContext, Task<FunctionCallAgentContext>> wrappedNext = async ctx => (FunctionCallAgentContext)await next(ctx);
            return await OnProcessAsync(callContext, wrappedNext, cancellationToken);
        }

        return await next(context);
    }

    public async Task<AgentRunContext> OnProcessAsync(AgentRunContext context, Func<AgentRunContext, Task<AgentRunContext>> next, CancellationToken cancellationToken = default)
    {
        // Pre-run logic
        var result = await next(context);
        // Post-run logic
        return result;
    }

    public async Task<FunctionCallAgentContext> OnProcessAsync(FunctionCallAgentContext context, Func<FunctionCallAgentContext, Task<FunctionCallAgentContext>> next, CancellationToken cancellationToken = default)
    {
        // Pre-function call logic
        var result = await next(context);
        // Post-function call logic
        return result;
    }
}
```

#### Pros
- Simple grouping of filters in the same list, help with DI registration and filtering iteration
- Lower maintenance and learning curve when adding new filter types
- Can be combined with other patterns like the `AgentFilterProcessor`

#### Cons
- Less clear separation of concerns compared to dedicated filter types
- Requires extra runtime type checking and casting for context-specific processing

## Decision Outcome

Chosen option: To be determined after further discussion and evaluation of the pros and cons of each option.
