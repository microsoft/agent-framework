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

## Other AI Agent Framework Analysis

This section provides an analysis of how other major AI agent frameworks handle filtering, middleware, hooks, or similar interception capabilities. The goal is to identify ubiquitous language, design patterns, and approaches that could inform our Agent Middleware design also providing valuable insights into achieving a more idiomatic designs.

### Overview Comparison Table

| Provider                  | Language | Supports (Y/N) | Naming                          | TL;DR Observation |
|---------------------------|----------|----------------|---------------------------------|------------------------|
| LangChain (Python)       | Python  | Y (read/write) | Callbacks (BaseCallbackHandler) | Uses observer pattern with event methods for interception (e.g., on_chain_start); supports agent actions and errors; handlers can read inputs/outputs and modify metadata or raise exceptions to influence flow. [Details](#langchain) |
| LangChain (JS)           | JS      | Y (read/write) | Callbacks (BaseCallbackHandler) | Similar observer pattern to Python, with event methods adapted for JS async handling; supports chain/agent interception; handlers can read inputs/outputs and modify metadata or raise exceptions to influence flow. [Details](#langchain) |
| LangGraph                | Python  | Y (read/write) | Hooks/Callbacks (inherited from LangChain) | Event-driven with runtime handlers; integrates callbacks for observability in graphs; inherits LangChain's ability to read/modify metadata or interrupt execution. [Details](#langgraph) |
| AutoGen (Python)         | Python  | Y (read/write) | Reply Functions (register_reply) | Reply functions intercept and process messages; middleware-like for agent replies; can directly modify messages or replies before continuing. [Details](#autogen) |
| AutoGen (C#)             | C#      | Y (read/write) | Middleware (MiddlewareAgent)   | Decorator/wrapper with middleware delegates for message modification; delegates can read and alter message content or options. [Details](#autogen) |
| Semantic Kernel (C#)     | C#      | Y (read/write) | Filters (IFunctionInvocationFilter, etc.) | Interface-based processor pattern for function/prompt interception; filters can read and modify context, arguments, or results. [Details](#semantic-kernel) |
| Semantic Kernel (Python) | Python  | Y (read/write) | Filters (add_filter, @kernel.filter decorator) | Function and decorator-based for interception; no explicit interfaces like C#, focuses on async functions for filters; can read and modify context/arguments/results. [Details](#semantic-kernel) |
| Semantic Kernel (Java)   | Java    | Y (read/write) | Filters (FunctionInvocationFilter, etc.) | Interface-based similar to C#, adapted for Java's functional interfaces; supports function invocation interception; can read and modify context/arguments/results. [Details](#semantic-kernel) |
| CrewAI                   | Python  | Y (read)       | Events/Callbacks (BaseEventListener) | Event-driven orchestration with listeners for workflows; listeners can observe events (e.g., read source/event data) but are primarily for logging/reactions without direct modification of workflow state. [Details](#crewai) |
| LlamaIndex               | Python  | Y (read)       | Callbacks (BaseCallbackHandler) | Observer pattern with event methods for queries and tools; handlers can observe events/payloads (e.g., read prompts/responses) but are designed for debugging/tracing without modifying execution context. [Details](#llamaindex) |
| Haystack                 | Python  | N (Pipeline-based interception) | N/A (Pipeline Components/Routers) | Relies on modular pipelines for implicit interception but lacks explicit middleware/filters; custom components can read/write data flow via routing/transformations, but this is compositional rather than hook-based interception. [Details](#haystack) |
| OpenAI Swarm             | Python  | N              | N/A                             | No explicit middleware/filters; interception requires custom wrappers or manual handling (e.g., function decorators, client subclassing), lacking native framework support for built-in components to accept such modifications. [Details](#openai-swarm) |
| Atomic Agents            | Python  | N              | N/A (Composable Components)     | No explicit middleware/filters; modularity allows composable units but no dedicated interception hooks or callbacks for custom reading/modification mid-execution. [Details](#atomic-agents) |
| Smolagents (Hugging Face)| Python  | N              | N/A                             | No explicit support; focuses on simple agent building without interception mechanisms or hooks for reading/modifying execution. [Details](#smolagents) |
| Phidata (Agno)           | Python  | N              | N/A                             | No explicit middleware/filters; agents use tools/memory but no interception hooks for custom reading/modification of calls. [Details](#phidata) |
| PromptFlow (Microsoft)   | Python  | N (Tracing only) | Tracing                         | Supports tracing for LLM interactions, acting as callbacks for debugging/iteration; tracing is read-only for observability/telemetry without options to modify context or intercept calls beyond logging. [Details](#promptflow) |
| n8n                      | JS/TS   | Y (read/write) | Callbacks (inherited from LangChain) | AI Agent node uses LangChain under the hood, inheriting callbacks for observability; supports reading/modifying metadata or interrupting flow as in LangChain. [Details](#n8n) |

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
    public async Task OnRunAsync(AgentRunContext context, Func<AgentRunContext, Task> next, CancellationToken cancellationToken = default)
    {
        // Pre-run logic

        await next(context);

        // Post-run logic
    }
}

public interface IAgentRunFilter
{
    Task OnRunAsync(AgentRunContext context, Func<AgentRunContext, Task> next, CancellationToken cancellationToken = default);
}

public interface IAgentFunctionCallFilter
{
    Task OnFunctionCallAsync(AgentFunctionCallContext context, Func<AgentFunctionCallContext, Task> next, CancellationToken cancellationToken = default);
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
        await _filterProcessor.ProcessAsync(context, async ctx =>
        {
            // Core agent logic - implement actual agent execution here
            var response = await this.ExecuteCoreLogicAsync(ctx.Messages, ctx.Thread, ctx.Options, cancellationToken);
            ctx.Response = response;
        }, cancellationToken);

        // Extract the response from the context
        return context.Response ?? throw new InvalidOperationException("Agent execution did not produce a response");
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
- Composable and reusable filter components

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
        await _runFilters.OnRunAsync(context, async ctx =>
        {
            // Core agent logic
            var response = await _innerAgent.RunAsync(ctx.Messages, ctx.Thread, ctx.Options, cancellationToken);
            ctx.Response = response;
        }, cancellationToken);

        // Extract the response from the context
        return context.Response ?? throw new InvalidOperationException("Agent execution did not produce a response");
    }
}
```

#### Pros
- Clean separation of concerns
- Follows established patterns in `Microsoft.Extensions.AI`
- Non-intrusive to existing agent implementations
- Supports both manual and DI configuration
- Context-specific processing middleware
- Composable and reusable filter components

#### Cons
- Additional wrapper class adds complexity
- Requires explicit wrapping of agents
- Only viable for `ChatClientAgents` as other agents implementation will not have visibility/knowledge of the function call filters.

### Option 3: Dedicated Processor Component for Middleware

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
    // For thread-safety when used as a Singleton
    private readonly ConcurrentBag<IAgentFilter> _filters = new(); 

    public void AddFilter(IAgentFilter filter) 
        => _filters.Add(filter);

    public IEnumerable<IAgentFilter> GetFiltersForContext<T>() where T : AgentContext
        => _filters.Where(f => f.CanProcess(typeof(T));

    public async Task ProcessAsync<T>(T context, Func<T, Task> coreLogic, CancellationToken ct = default) where T : AgentContext
    {
        var applicable = GetFiltersForContext<T>().ToList(); // Sorted
        await InvokeChainAsync(context, applicable, 0, coreLogic, ct);
    }

    private async Task InvokeChainAsync<T>(T context, IList<IAgentFilter> filters, int index, Func<T, Task> coreLogic, CancellationToken ct) where T : AgentContext
    {
        if (index < filters.Count)
        {
            await filters[index].OnProcessAsync(
                context, 
                async ctx => await InvokeChainAsync((T)ctx, filters, index + 1, coreLogic, ct), 
                ct);
        }
        else
        {
            await coreLogic(context);
        }
    }
}
```

#### Pros
- Flexibility: Use shared processor for multiple agents or create per-agent instances.
- Querying: Agents can inspect/trigger filters dynamically via GetFiltersForContext.
- Extensibility: Add new contexts/filters without changing agent or processor much (just implement IAgentFilter<TNewContext>).
- Simplicity: No decorators; agents stay lean. Generic filters reduce interface explosion.

#### Cons
- Introducing a separate processor class creates an extra layer between the agent and its filters

## APPENDIX 1: Proposed Middleware Contexts

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
    public AgentRunResponse? Response { get; set; }
    public AgentThread? Thread { get; }

    public AgentRunContext(AIAgent agent, IList<ChatMessage> messages, AgentThread? thread, AgentRunOptions? options)
        : base(agent, options)
    {
        Messages = messages;
        Thread = thread;
    }
}

public class AgentFunctionInvocationContext : AgentToolContext
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

## APPENDIX 2: Setting Up Middleware Options

### 1. Semantic Kernel Setup

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
    Task OnRunAsync(AgentRunContext context, Func<AgentRunContext, Task> next, CancellationToken cancellationToken = default);
}
interface IAgentFunctionCallFilter
{
    Task OnFunctionCallAsync(AgentFunctionCallContext context, Func<AgentFunctionCallContext, Task> next, CancellationToken cancellationToken = default);
}
```

#### Pros
- Clean separation of concerns
- Follows established patterns in Semantic Kernel and easy migration path
- No resistance or complaints from the community when used in Semantic Kernel

#### Cons
- Adding more filters may require adding more properties to the agent/processor class.
- Adding more filters requires bigger code changes downstream to callers.

### 2. Setup with Generic Method

Instead of properties, exposing as a method may be more appropriate while still maintaining those filters in separate buckets internally.

```csharp
// Use Case
var agent = new MyAgent();
agent.AddFilters<RunFilter>([new MyAgentRunFilter(), new MyMultipleFilterImplementation()]);
agent.AddFilters<FunctionCallFilter>([new MyAgentFunctionCallFilter(), new MyMultipleFilterImplementation()]);
agent.AddFilters<AYZFilter>([new MyAgentAYZFilter(), new MyMultipleFilterImplementation()]);

```

#### Pros
- Clean separation of concerns
- Cleaner API for adding filters compared to option 1
- No resistance or complaints from the community when used in Semantic Kernel

#### Cons
- Adding more filters may require adding more properties to the agent/processor class.
- Adding more filters requires bigger code changes downstream to callers.

### 3. Setup with Filter Hierarchy, Fully Generic Setup

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

// OR Via constructor (Also DI Friendly)
var agent = new MyAgent(new List<IAgentFilter> { 
    new MyAgentRunFilter(), 
    new MyAgentFunctionCallFilter(), 
    new MyAgentAYZFilter(), 
    new MyMultipleFilterImplementation() });

// Impl
interface IAgentFilter
{
    bool CanProcess(AgentContext context);
    Task OnProcessAsync(AgentContext context, Func<AgentContext, Task> next, CancellationToken cancellationToken = default);
}

interface IAgentFilter<T> : IAgentFilter where T : AgentContext
{
    Task OnProcessAsync(T context, Func<T, Task> next, CancellationToken cancellationToken = default);
}

class MySingleFilterImplementation : IAgentFilter<AgentRunContext>
{
    public bool CanProcess(AgentContext context)
        => context is AgentRunContext;

    public async Task OnProcessAsync(AgentContext context, Func<AgentContext, Task> next, CancellationToken cancellationToken = default)
    {
        Func<AgentRunContext, Task> wrappedNext = async ctx => await next(ctx);
        await OnProcessAsync((AgentRunContext)context, wrappedNext, cancellationToken);
    }

    public async Task OnProcessAsync(AgentRunContext context, Func<AgentRunContext, Task> next, CancellationToken cancellationToken = default)
    {
        // Pre-run logic
        await next(context);
        // Post-run logic
    }
}

class MyMultipleFilterImplementation : IAgentFilter<AgentRunContext>, IAgentFilter<FunctionCallAgentContext>
{
    public bool CanProcess(AgentContext context)
        => context is AgentRunContext or FunctionCallAgentContext;

    public async Task OnProcessAsync(AgentContext context, Func<AgentContext, Task> next, CancellationToken cancellationToken = default)
    {
        if (context is AgentRunContext runContext)
        {
            Func<AgentRunContext, Task> wrappedNext = async ctx => await next(ctx);
            await OnProcessAsync(runContext, wrappedNext, cancellationToken);
            return;
        }

        if (context is FunctionCallAgentContext callContext)
        {
            Func<FunctionCallAgentContext, Task> wrappedNext = async ctx => await next(ctx);
            await OnProcessAsync(callContext, wrappedNext, cancellationToken);
            return;
        }

        await next(context);
    }

    public async Task OnProcessAsync(AgentRunContext context, Func<AgentRunContext, Task> next, CancellationToken cancellationToken = default)
    {
        // Pre-run logic
        await next(context);
        // Post-run logic
    }

    public async Task OnProcessAsync(FunctionCallAgentContext context, Func<FunctionCallAgentContext, Task> next, CancellationToken cancellationToken = default)
    {
        // Pre-function call logic
        await next(context);
        // Post-function call logic
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

## Appendix: Other Considerations
