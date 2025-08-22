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
    public Task OnRunAsync(AgentRunContext context, Func<AgentRunContext, Task> next)
    {
        // Pre-run logic
        
        await next(context);
        
        // Post-run logic

        return Task.CompletedTask;
    }
}

public interface IAgentRunFilter
{
    Task OnRunAsync(AgentRunContext context, Func<AgentRunContext, Task> next);
}

public interface IAgentFunctionCallFilter
{
    Task OnFunctionCallAsync(AgentFunctionCallContext context, Func<AgentFunctionCallContext, Task> next);
}

public class AIAgent
{
    private List<IAgentRunFilter> _runFilters = [];
    private List<IAgentFunctionCallFilter> _functionCallFilters = [];

    public AIAgent(IServiceProvider serviceProvider)
    {
        // Resolve filters from DI
        _runFilters ??= serviceProvider.GetServices<IAgentRunFilter>()?.ToList();
        _functionCallFilters ??= serviceProvider.GetServices<IAgentFunctionCallFilter>()?.ToList();
    }

    public virtual Task<AgentResponse> RunAsync(AgentRunOptions options, AgentThread? thread = null)
    {
        var context = new AgentRunContext(options, thread);

        // Wrap core logic in filter pipeline
        return _filters.OnRunAsync(runContext, ctx =>
        {
            // Core agent logic
            return Task.FromResult(ctx);
        });
    }
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
    private List<IAgentRunFilter> _runFilters = [];
    private List<IAgentFunctionCallFilter> _functionCallFilters = [];

    public FilteringAIAgent(AIAgent agent, IServiceProvider serviceProvider)
    {
        _innerAgent = agent;

        // Resolve filters from DI
        _runFilters ??= serviceProvider.GetServices<IAgentRunFilter>()?.ToList();
        _functionCallFilters ??= serviceProvider.GetServices<IAgentFunctionCallFilter>()?.ToList();
    }

    public virtual Task<AgentResponse> RunAsync(AgentRunOptions options, AgentThread? thread = null, CancellationToken cancellationToken = default)
    {
        var context = new AgentRunContext(options, thread);

        // Wrap core logic in filter pipeline
        return _runFilters.OnRunAsync(runContext, ctx =>
        {
            // Core agent logic
            return _innerAgent.RunAsync(ctx.Messages, ctx.Options, cancellationToken);
        });
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
    Task OnRunAsync(AgentRunContext context, Func<AgentRunContext, Task> next); 
}
interface IAgentFunctionCallFilter  
{
    Task OnFunctionCallAsync(AgentFunctionCallContext context, Func<AgentFunctionCallContext, Task> next); 
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
    Task OnProcessAsync(AgentContext context, Func<AgentContext, Task> next); 
}

interface IAgentFilter<T> : IAgentFilter where T : AgentContext
{
    Task OnProcessAsync(T context, Func<T, Task> next);
}

class MySingleFilterImplementation : IAgentFilter<RunAgentContext>
{
    public bool CanProcess(AgentContext context) 
        => context is RunAgentContext;

    public Task OnProcessAsync(AgentContext context, Func<AgentContext, Task> next)
    {
        Func<RunAgentContext, Task> wrappedNext = ctx => next(ctx);
        return OnProcessAsync((RunAgentContext)context, wrappedNext);
    }

    public Task OnProcessAsync(RunAgentContext context, Func<RunAgentContext, Task> next) 
    {
        // Pre-run logic
        await next(context);
        // Post-run logic
        return Task.CompletedTask;
    }
}

class MyMultipleFilterImplementation : IAgentFilter<RunAgentContext>, IAgentFilter<FunctionCallAgentContext>
{
    public bool CanProcess(AgentContext context) 
        => context is RunAgentContext or FunctionCallAgentContext;

    public Task OnProcessAsync(AgentContext context, Func<AgentContext, Task> next)
    {
        if (context is RunAgentContext runContext)
        {
            Func<RunAgentContext, Task> wrappedNext = ctx => next(ctx);
            return OnProcessAsync(runContext, wrappedNext);
        }
        
        if (context is FunctionCallAgentContext callContext)
        {
            Func<FunctionCallAgentContext, Task> wrappedNext = ctx => next(ctx);
            return OnProcessAsync(callContext, wrappedNext);
        }
    }

    public Task OnProcessAsync(RunAgentContext context, Func<RunAgentContext, Task> next) 
    {
        // Pre-run logic
        await next(context);
        // Post-run logic
        return Task.CompletedTask;
    }

    public Task OnProcessAsync(FunctionCallAgentContext context, Func<FunctionCallAgentContext, Task> next) 
    {
        // Pre-function call logic
        await next(context);
        // Post-function call logic
        return Task.CompletedTask;
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
