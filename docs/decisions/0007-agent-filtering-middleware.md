---
status: proposed
contact: rogerbarreto
date: 2025-09-15
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
| LangChain (Python)       | Python  | Y (read) | Callbacks (BaseCallbackHandler) | Uses observer pattern with event methods for interception (e.g., on_chain_start); supports agent actions and errors; handlers can read inputs/outputs and modification is limited to the parameters or by raising exceptions to influence flow. [Details](#langchain) |
| LangChain (JS)           | JS      | Y (read/write) | Callbacks (BaseCallbackHandler) | Similar observer pattern to Python, with event methods adapted for JS async handling; supports chain/agent interception; handlers can read inputs/outputs and modify metadata or raise exceptions to influence flow. [Details](#langchain) |
| LangChain            | JS/Python/TS      | Y (read/write) | Middleware | Middleware concept was recently introduced in LangChain 1.0 alpha; [Details](https://blog.langchain.com/agent-middleware/) |
| LangGraph                | Python  | Y (read/write) | Hooks/Callbacks (inherited from LangChain) | Event-driven with runtime handlers; integrates callbacks for observability in graphs; inherits LangChain's ability to read/modify metadata or interrupt execution. [Details](#langgraph) |
| AutoGen (Python)         | Python  | Y (read/write) | Reply Functions (register_reply) | Reply functions intercept and process messages; middleware-like for agent replies; can directly modify messages or replies before continuing. [Details](#autogen) |
| AutoGen (C#)             | C#      | Y (read/write) | Middleware (MiddlewareAgent)   | Decorator/wrapper with middleware delegates for message modification; delegates can read and alter message content or options. [Details](#autogen) |
| Semantic Kernel (C#)     | C#      | Y (read/write) | Filters (IFunctionInvocationFilter, etc.) | Interface-based middleware pattern for function/prompt interception; filters can read and modify context, arguments, or results. [Details](#semantic-kernel) |
| Semantic Kernel (Python) | Python  | Y (read/write) | Filters (add_filter, @kernel.filter decorator) | Function and decorator-based for interception; no explicit interfaces like C#, focuses on async functions for filters; can read and modify context/arguments/results. [Details](#semantic-kernel) |
| CrewAI                   | Python  | Y (read)       | Events/Callbacks (BaseEventListener) | Event-driven orchestration with listeners for workflows; listeners can observe events (e.g., read source/event data) but are primarily for logging/reactions without direct modification of workflow state. [Details](#crewai) |
| LlamaIndex               | Python  | Y (read)       | Callbacks (CallbackManager) | Observer pattern with event methods for queries and tools; handlers can observe events/payloads (e.g., read prompts/responses) but are designed for debugging/tracing without modifying execution context. [Details](#llamaindex) |
| Haystack                 | Python  | N (Pipeline-based interception) | N/A (Pipeline Components/Routers) | Relies on modular pipelines for implicit interception but lacks explicit middleware/filters; custom components can read/write data flow via routing/transformations, but this is compositional rather than hook-based interception. [Details](#haystack) |
| OpenAI Swarm             | Python  | N              | N/A                             | No explicit middleware/filters; interception requires custom wrappers or manual handling (e.g., function decorators, client subclassing), lacking native framework support for built-in components to accept such modifications. [Details](#openai-swarm) |
| Atomic Agents            | Python  | N              | N/A (Composable Components)     | No explicit middleware/filters; modularity allows composable units but no dedicated interception hooks or callbacks for custom reading/modification mid-execution. [Details](#atomic-agents) |
| Smolagents (Hugging Face)| Python  | N              | N/A                             | No explicit support; focuses on simple agent building without interception mechanisms or hooks for reading/modifying execution. [Details](#smolagents-hugging-face) |
| Phidata (Agno)           | Python  | N              | N/A                             | No explicit middleware/filters; agents use tools/memory but no interception hooks for custom reading/modification of calls. [Details](#phidata-agno) |
| PromptFlow (Microsoft)   | Python  | N (Tracing only) | Tracing                         | Supports tracing for LLM interactions, acting as callbacks for debugging/iteration; tracing is read-only for observability/telemetry without options to modify context or intercept calls beyond logging. [Details](#promptflow-microsoft) |
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

    public async Task<AgentResponse> RunAsync(
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

    protected abstract Task<AgentResponse> ExecuteCoreLogicAsync(
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

Similar to the `OpenTelemetryAgent` and the `DelegatingChatClient` in `Microsoft.Extensions.AI`, this option involves creating decorator agents that wrap the inner agent and allow interception of method calls. The current POC implementation demonstrates two approaches:

#### 2a. Direct Decorator Implementation (GuardrailCallbackAgent)

```csharp
// Current POC implementation from samples
var agent = persistentAgentsClient.CreateAIAgent(model).AsBuilder()
    .Use((innerAgent) => new GuardrailCallbackAgent(innerAgent)) // Decoration based agent run handling
    .Use(async (context, next) => // Context based handling
    {
        // Guardrail: Filter input messages for PII
        context.Messages = context.Messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();
        Console.WriteLine($"Pii Middleware - Filtered messages: {new ChatResponse(context.Messages).Text}");

        await next(context);

        if (!context.IsStreaming)
        {
            // Guardrail: Filter output messages for PII
            context.Messages = context.Messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();
        }
        else
        {
            context.SetRawResponse(StreamingPiiDetectionAsync(context.RunStreamingResponse!));
        }
    })
    .Build();

// Direct decorator implementation
internal sealed class GuardrailCallbackAgent : DelegatingAIAgent
{
    private readonly string[] _forbiddenKeywords = { "harmful", "illegal", "violence" };

    public GuardrailCallbackAgent(AIAgent innerAgent) : base(innerAgent) { }

    public override async Task<AgentResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        var filteredMessages = this.FilterMessages(messages);
        Console.WriteLine($"Guardrail Middleware - Filtered messages: {new ChatResponse(filteredMessages).Text}");

        var response = await this.InnerAgent.RunAsync(filteredMessages, thread, options, cancellationToken);

        response.Messages = response.Messages.Select(m => new ChatMessage(m.Role, this.FilterContent(m.Text))).ToList();

        return response;
    }

    public override async IAsyncEnumerable<AgentResponseUpdate> RunStreamingAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var filteredMessages = this.FilterMessages(messages);
        await foreach (var update in this.InnerAgent.RunStreamingAsync(filteredMessages, thread, options, cancellationToken))
        {
            if (update.Text != null)
            {
                yield return new AgentResponseUpdate(update.Role, this.FilterContent(update.Text));
            }
            else
            {
                yield return update;
            }
        }
    }

    private List<ChatMessage> FilterMessages(IEnumerable<ChatMessage> messages)
    {
        return messages.Select(m => new ChatMessage(m.Role, this.FilterContent(m.Text))).ToList();
    }

    private string FilterContent(string content)
    {
        foreach (var keyword in this._forbiddenKeywords)
        {
            if (content.Contains(keyword, StringComparison.OrdinalIgnoreCase))
            {
                return "[REDACTED: Forbidden content]";
            }
        }
        return content;
    }
}
```

#### 2b. Context-Based Middleware (RunningCallbackHandlerAgent)

The POC also includes a context-based approach using `RunningCallbackHandlerAgent` that wraps the agent and provides a context object for middleware processing:

```csharp
// Internal implementation that supports the .Use() pattern
internal sealed class RunningCallbackHandlerAgent : DelegatingAIAgent
{
    private readonly Func<AgentInvokeCallbackContext, Func<AgentInvokeCallbackContext, Task>, Task> _func;

    internal RunningCallbackHandlerAgent(AIAgent innerAgent, Func<AgentInvokeCallbackContext, Func<AgentInvokeCallbackContext, Task>, Task> func) : base(innerAgent)
    {
        this._func = func;
    }

    public override async Task<AgentResponse> RunAsync(IEnumerable<ChatMessage> messages, AgentThread? thread = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
    {
        var context = new AgentInvokeCallbackContext(this, messages, thread, options, isStreaming: false, cancellationToken);

        async Task CoreLogicAsync(AgentInvokeCallbackContext ctx)
        {
            var response = await this.InnerAgent.RunAsync(ctx.Messages, ctx.Thread, ctx.Options, ctx.CancellationToken);
            ctx.SetRawResponse(response);
        }

        await this._func(context, CoreLogicAsync);

        return context.RunResponse!;
    }
}
```

#### 2c. Function Invocation Filtering 

The POC also demonstrates function invocation filtering using a similar decorator pattern:

```csharp
// Function invocation middleware using .Use() pattern
var agent = persistentAgentsClient.CreateAIAgent(model)
    .AsBuilder()
    .Use((functionInvocationContext, next, ct) =>
    {
        Console.WriteLine($"IsStreaming: {functionInvocationContext!.IsStreaming}");
        return next(functionInvocationContext.Arguments, ct);
    })
    .Use((functionInvocationContext, next, ct) =>
    {
        Console.WriteLine($"City Name: {(functionInvocationContext!.Arguments.TryGetValue("location", out var location) ? location : "not provided")}");
        return next(functionInvocationContext.Arguments, ct);
    })
    .Build();
```

This demonstrates that the current POC supports both agent-level and function-level filtering through consistent patterns.

#### Pros
- Clean separation of concerns
- Follows established patterns in `Microsoft.Extensions.AI` (DelegatingChatClient, OpenTelemetryAgent)
- Non-intrusive to existing agent implementations
- Supports both manual and DI configuration through builder pattern
- Context-specific processing middleware with `AgentInvokeCallbackContext`
- Composable and reusable filter components
- Flexible implementation allowing both direct decorators and context-based middleware
- Seamless integration with builder pattern using `.Use()` method
- Support for both streaming and non-streaming scenarios
- Rich context object providing access to messages, thread, options, and response handling

### Option 3: Dedicated Processor Component for Middleware

This approach involves creating a dedicated `CallbackMiddlewareProcessor` that manages collections of `ICallbackMiddleware` instances. The current POC implementation demonstrates this pattern with the `CallbackEnabledAgent` and processor architecture.

#### Current POC Implementation

```csharp
// Current POC usage from samples
var agent = persistentAgentsClient.CreateAIAgent(model)
    .AsBuilder()
    .UseCallbacks(config =>
    {
        config.AddCallback(new PiiDetectionMiddleware());
        config.AddCallback(new GuardrailCallbackMiddleware());
    }).Build();

// Middleware implementation
internal sealed class PiiDetectionMiddleware : CallbackMiddleware<AgentInvokeCallbackContext>
{
    public override async Task OnProcessAsync(AgentInvokeCallbackContext context, Func<AgentInvokeCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        // Guardrail: Filter input messages for PII
        context.Messages = context.Messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();
        Console.WriteLine($"Pii Middleware - Filtered messages: {new ChatResponse(context.Messages).Text}");
        await next(context);

        if (!context.IsStreaming)
        {
            // Guardrail: Filter output messages for PII
            context.Messages = context.Messages.Select(m => new ChatMessage(m.Role, FilterPii(m.Text))).ToList();
        }
        else
        {
            context.SetRawResponse(StreamingPiiDetectionAsync(context.RunStreamingResponse!));
        }
    }

    private static string FilterPii(string content)
    {
        // PII detection logic...
    }
}

internal sealed class GuardrailCallbackMiddleware : CallbackMiddleware<AgentInvokeCallbackContext>
{
    private readonly string[] _forbiddenKeywords = { "harmful", "illegal", "violence" };

    public override async Task OnProcessAsync(AgentInvokeCallbackContext context, Func<AgentInvokeCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        // Guardrail: Filter input messages for forbidden content
        context.Messages = this.FilterMessages(context.Messages);
        Console.WriteLine($"Guardrail Middleware - Filtered messages: {new ChatResponse(context.Messages).Text}");

        await next(context);
        if (!context.IsStreaming)
        {
            // Guardrail: Filter output messages for forbidden content
            context.Messages = this.FilterMessages(context.Messages);
        }
        else
        {
            context.SetRawResponse(StreamingGuardRailAsync(context.RunStreamingResponse!));
        }
    }
}
```

#### Function Invocation Filtering

The POC also demonstrates function invocation filtering using the processor pattern:

```csharp
// Processor-based function invocation middleware
var agent = persistentAgentsClient.CreateAIAgent(model)
    .AsBuilder()
    .UseCallbacks(config =>
    {
        config.AddCallback(new UsedApiFunctionInvocationCallback());
        config.AddCallback(new CityInformationFunctionInvocationCallback());
    }).Build();

internal sealed class UsedApiFunctionInvocationCallback : CallbackMiddleware<AgentFunctionInvocationCallbackContext>
{
    public override async Task OnProcessAsync(AgentFunctionInvocationCallbackContext context, Func<AgentFunctionInvocationCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        Console.WriteLine($"IsStreaming: {context!.IsStreaming}");

        await next(context);
    }
}

internal sealed class CityInformationFunctionInvocationCallback : CallbackMiddleware<AgentFunctionInvocationCallbackContext>
{
    public override async Task OnProcessAsync(AgentFunctionInvocationCallbackContext context, Func<AgentFunctionInvocationCallbackContext, Task> next, CancellationToken cancellationToken)
    {
        Console.WriteLine($"City Name: {(context!.Arguments.TryGetValue("location", out var location) ? location : "not provided")}");
        await next(context);
    }
}
```

This demonstrates that the current POC supports both agent-level and function-level filtering through consistent patterns.

#### Processor Implementation

The `CallbackMiddlewareProcessor` manages the filter pipeline and chain execution:

```csharp
public sealed class CallbackMiddlewareProcessor
{
    // For thread-safety when used as a Singleton
    private readonly ConcurrentBag<ICallbackMiddleware> _agentCallbacks = [];

    public CallbackMiddlewareProcessor(IEnumerable<ICallbackMiddleware>? callbacks = null)
    {
        if (callbacks is not null)
        {
            foreach (var callback in callbacks)
            {
                AddCallback(callback);
            }
        }
    }

    internal CallbackMiddlewareProcessor AddCallback(ICallbackMiddleware middleware)
    {
        switch (middleware)
        {
            case CallbackMiddleware<AgentInvokeCallbackContext>:
                this._agentCallbacks.Add(middleware);
                break;
            default:
                throw new ArgumentException($"The middleware type '{middleware.GetType().FullName}' is not supported.", nameof(middleware));
        }

        return this;
    }

    public async Task ProcessAsync<TContext>(TContext context, Func<TContext, Task> coreLogic, CancellationToken cancellationToken = default)
        where TContext : CallbackContext
    {
        var applicableCallbacks = this.GetApplicableCallbacks<TContext>().ToList();
        await this.InvokeChainAsync(context, applicableCallbacks, 0, coreLogic, cancellationToken);
    }

    private IEnumerable<ICallbackMiddleware> GetApplicableCallbacks<TContext>()
        where TContext : CallbackContext
    {
        return this._agentCallbacks.Where(callback => callback.CanProcess<TContext>());
    }
}
```

#### CallbackEnabledAgent Implementation

```csharp
public sealed class CallbackEnabledAgent : DelegatingAIAgent
{
    private readonly CallbackMiddlewareProcessor _callbacksProcessor;

    public CallbackEnabledAgent(AIAgent agent, CallbackMiddlewareProcessor? callbackMiddlewareProcessor) : base(agent)
    {
        this._callbacksProcessor = callbackMiddlewareProcessor ?? new();
    }

    public override async Task<AgentResponse> RunAsync(
        IEnumerable<ChatMessage> messages,
        AgentThread? thread = null,
        AgentRunOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        AgentInvokeCallbackContext roamingContext = null!;

        async Task CoreLogic(AgentInvokeCallbackContext ctx)
        {
            roamingContext ??= ctx;
            var result = await this.InnerAgent.RunAsync(ctx.Messages, ctx.Thread, ctx.Options, ctx.CancellationToken);

            ctx.SetRawResponse(result);
        }

        await this._callbacksProcessor.ProcessAsync<AgentInvokeCallbackContext>(
            new AgentInvokeCallbackContext(
                agent: this,
                messages: messages,
                thread,
                options,
                isStreaming: false,
                cancellationToken),
            CoreLogic,
            cancellationToken);

        return roamingContext.RunResponse!;
    }
}
```

#### Pros
- Flexibility: Use shared processor for multiple agents or create per-agent instances
- Clean fluent configuration API with `.UseCallbacks()` builder method
- Type-safe middleware registration with `CallbackMiddleware<TContext>` base class
- Thread-safe processor implementation using `ConcurrentBag<ICallbackMiddleware>`
- Extensible context system with `AgentInvokeCallbackContext` providing rich execution context
- Seamless integration with existing agent builder pattern
- Support for both streaming and non-streaming scenarios in middleware
- Clear separation between middleware logic and agent core functionality
- Simplicity: Agents stay lean, middleware is externalized to processor
- Extensibility: Add new contexts/filters without changing agent implementation

#### Cons
- Additional complexity with processor class and context management
- Requires understanding of middleware lifecycle and context passing
- Type switching in processor for different middleware types
- Roaming context pattern needed to capture specialized contexts through middleware chain

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
    public AgentResponse? Response { get; set; }
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

- **Option 2 (Decorator Pattern)** is the preferred approach for the following reasons:
  - Adding a processor pattern seems an overkill as we can achieve same results without introducing new abstractions and complexity.
  - Direct decorator on agents and tools for agent and function invocation middleware.
  - Support for Context-based middleware also leveraging closer patterns to Semantic Kernel filters.
  - Agent Builder pattern integration with `.Use()` method for fluent configuration

**Key POC Insights**:
1. Both patterns actually work
2. The decorator pattern offers more direct control and simpler and more flexible implementation
2. The processor seems an overkill compared to decorator as it adds more extra abstractions and complexity
4. Function invocation filtering is supported in both patterns
5. Streaming scenarios are well-supported in both approaches
6. Function approval request filtering is supported in both patterns
7. Builder pattern added as part of the POC is a must-have and mades both approaches developer-friendly

## Appendix: Other AI Agent Framework Analysis Details

#### LangChain

LangChain uses callbacks for interception, which can be passed at runtime or during construction.

Naming (Python): Callbacks (BaseCallbackHandler)  
Supports: Y (read/write)  
Observation: Uses observer pattern with event methods for interception (e.g., on_chain_start); supports agent actions and errors; handlers can read inputs/outputs and modify metadata or raise exceptions to influence flow.

**Python Example:** For more details, see the official documentation: [Callbacks - Python LangChain](https://python.langchain.com/docs/concepts/callbacks/).

```python
from langchain_core.callbacks import BaseCallbackHandler

class MyHandler(BaseCallbackHandler):
    def on_chain_start(self, serialized, inputs, **kwargs):
        inputs['number'] += 1  # Modify inputs (write capability)
        print("Chain started!")

handler = MyHandler()

# Pass callback at runtime
chain.invoke({"number": 25}, {"callbacks": [handler]})

# Or at constructor time
chain = SomeChain(callbacks=[handler])
chain.invoke({"number": 25})
```

Naming (JS): Callbacks (BaseCallbackHandler)  
Supports: Y (read/write)  
Observation: Similar observer pattern to Python, with event methods adapted for JS async handling; supports chain/agent interception; handlers can read inputs/outputs and modify metadata or raise exceptions to influence flow.

**JS Example:** For more details, see the official documentation: [Callbacks - LangChain.js](https://js.langchain.com/docs/concepts/callbacks/). (Adapted for async handling in JS.)

```javascript
import { BaseCallbackHandler } from "@langchain/core/callbacks/base";

class MyHandler extends BaseCallbackHandler {
  name = "my_handler";

  async handleChainStart(chain, inputs) {
    inputs.number += 1;  # Modify inputs (write capability)
    console.log("Chain started!");
  }
}

const handler = new MyHandler();

// Pass callback at runtime
await chain.invoke({ number: 25 }, { callbacks: [handler] });

// Or at constructor time
const chainWithHandler = new SomeChain({ callbacks: [handler] });
await chainWithHandler.invoke({ number: 25 });
```

#### LangGraph

LangGraph inherits callbacks from LangChain and often uses them with handlers for observability (e.g., via Langfuse).

Naming (Python): Hooks/Callbacks (inherited from LangChain)  
Supports: Y (read/write)  
Observation: Event-driven with runtime handlers; integrates callbacks for observability in graphs; inherits LangChain's ability to read/modify metadata or interrupt execution.

For more details, see the official documentation (inherited from LangChain): [Callbacks - Python LangChain](https://python.langchain.com/docs/concepts/callbacks/). Here's an example of streaming with a callback handler (Python):

```python
from langfuse.langchain import CallbackHandler
from langchain_core.messages import HumanMessage

class MyLangfuseHandler(CallbackHandler):
    def on_chain_start(self, serialized, inputs, **kwargs):
        inputs['messages'][0].content += " modified"  # Modify input messages (write capability)
        super().on_chain_start(serialized, inputs, **kwargs)

langfuse_handler = MyLangfuseHandler()

# Stream with callback in config
for s in graph.stream(
    {"messages": [HumanMessage(content="What is Langfuse?")]},
    config={"callbacks": [langfuse_handler]}
):
    print(s)
```

#### AutoGen

AutoGen supports middleware-like behavior in both languages.

Naming (Python): Reply Functions (register_reply)  
Supports: Y (read/write)  
Observation: Reply functions intercept and process messages; middleware-like for agent replies; can directly modify messages or replies before continuing.

**Python Example:** For more details, see the official documentation: [agentchat.conversable_agent | AutoGen 0.2](https://microsoft.github.io/autogen/0.2/docs/reference/agentchat/conversable_agent). Uses `register_reply` to add reply functions that intercept and process messages.

```python
def print_messages(recipient, messages, sender, config): 
    if "callback" in config and config["callback"] is not None:
        callback = config["callback"]
        callback(sender, recipient, messages[-1])
    messages[-1]["content"] += " modified"  # Modify last message content (write capability)
    print(f"Messages sent to: {recipient.name} | num messages: {len(messages)}")
    return False, None  # required to ensure the agent communication flow continues

user_proxy.register_reply(
    [autogen.Agent, None],
    reply_func=print_messages, 
    config={"callback": None},
)

assistant.register_reply(
    [autogen.Agent, None],
    reply_func=print_messages, 
    config={"callback": None},
)
```

Naming (C#): Middleware (MiddlewareAgent)  
Supports: Y (read/write)  
Observation: Decorator/wrapper with middleware delegates for message modification; delegates can read and alter message content or options.

**C# Example:** For more details, see the official documentation: [Use middleware in an agent - AutoGen for .NET](https://microsoft.github.io/autogen-for-net/articles/Middleware-overview.html). Registers middleware to modify messages.

```csharp
// Register middleware to modify messages
var middlewareAgent = new MiddlewareAgent(innerAgent: agent);
middlewareAgent.Use(async (messages, options, agent, ct) =>
{
    if (messages.Last() is TextMessage lastMessage && lastMessage.Content.Contains("Hello World"))
    {
        lastMessage.Content = $"[middleware] {lastMessage.Content}";  # Modify message content (write capability)
        return lastMessage;
    }
    return await agent.GenerateReplyAsync(messages, options, ct);
});
```

#### Semantic Kernel

Semantic Kernel uses filters added to the kernel for interception during function invocation, prompt rendering, etc. Implementations differ by language: C# use interfaces, while Python uses functions and decorators.

Naming (C#): Filters (IFunctionInvocationFilter, etc.)  
Supports: Y (read/write)  
Observation: Interface-based middleware for function/prompt interception; filters can read and modify context, arguments, or results.

**C# Example:** For more details, see the official documentation: [Semantic Kernel Filters | Microsoft Learn](https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/filters). Adding a function invocation filter using interfaces.

```csharp
using Microsoft.SemanticKernel;

IKernelBuilder builder = Kernel.CreateBuilder();
builder.Services.AddSingleton<IFunctionInvocationFilter, LoggingFilter>();

Kernel kernel = builder.Build();

// Alternatively, add directly
kernel.FunctionInvocationFilters.Add(new LoggingFilter(logger));

// Define the filter
public sealed class LoggingFilter(ILogger logger) : IFunctionInvocationFilter
{
    public async Task OnFunctionInvocationAsync(FunctionInvocationContext context, Func<FunctionInvocationContext, Task> next)
    {
        context.Arguments["new_arg"] = "modified_value";  # Modify arguments by adding a new key (write capability)
        logger.LogInformation("Invoking {FunctionName}", context.Function.Name);
        await next(context);
        logger.LogInformation("Invoked {FunctionName}", context.Function.Name);
    }
}
```

Naming (Python): Filters (add_filter, @kernel.filter decorator)  
Supports: Y (read/write)  
Observation: Function and decorator-based for interception; no explicit interfaces like C#, focuses on async functions for filters; can read and modify context/arguments/results.

**Python Example:** For more details, see the official documentation: [Semantic Kernel Filters | Microsoft Learn](https://learn.microsoft.com/en-us/semantic-kernel/concepts/enterprise-readiness/filters). Adding function invocation filters (one as a standalone function and one via decorator).

```python
import logging
from typing import Callable, Coroutine, Any
from semantic_kernel import Kernel
from semantic_kernel.filters import FilterTypes, FunctionInvocationContext
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.contents import ChatHistory
from semantic_kernel.exceptions import OperationCancelledException

logger = logging.getLogger(__name__)

async def input_output_filter(
    context: FunctionInvocationContext,
    next: Callable[[FunctionInvocationContext], Coroutine[Any, Any, None]],
) -> None:
    if context.function.plugin_name != "chat":
        await next(context)
        return
    try:
        user_input = input("User:> ")
    except (KeyboardInterrupt, EOFError) as exc:
        raise OperationCancelledException("User stopped the operation") from exc
    if user_input == "exit":
        raise OperationCancelledException("User stopped the operation")
    context.arguments["chat_history"].add_user_message(user_input)  # Modify arguments by adding message (write capability)

    await next(context)

    if context.result:
        logger.info(f"Usage: {context.result.metadata.get('usage')}")
        context.arguments["chat_history"].add_message(context.result.value[0])
        print(f"Mosscap:> {context.result!s}")

kernel = Kernel()
kernel.add_service(AzureChatCompletion(service_id="chat-gpt"))

# Add filter as a standalone function
kernel.add_filter("function_invocation", input_output_filter)

# Add filter via decorator
@kernel.filter(filter_type=FilterTypes.FUNCTION_INVOCATION)
async def exception_catch_filter(
    context: FunctionInvocationContext, next: Coroutine[FunctionInvocationContext, Any, None]
):
    try:
        await next(context)
    except Exception as e:
        logger.info(e)

# Example invocation (assuming a "chat" plugin is added)
history = ChatHistory()
result = await kernel.invoke(
    function_name="chat",
    plugin_name="chat",
    chat_history=history,
)
```

#### CrewAI

CrewAI uses event listeners for callbacks.

Naming (Python): Events/Callbacks (BaseEventListener)  
Supports: Y (read)  
Observation: Event-driven orchestration with listeners for workflows; listeners can observe events (e.g., read source/event data) but are primarily for logging/reactions without direct modification of workflow state.

For more details, see the official documentation: [Event Listeners - CrewAI Documentation](https://docs.crewai.com/concepts/event-listener). Here's an example of setting up a custom listener (Python):

```python
from crewai.utilities.events import (
    CrewKickoffStartedEvent,
    BaseEventListener,
    crewai_event_bus
)

class MyCustomListener(BaseEventListener):
    def setup_listeners(self, crewai_event_bus):
        @crewai_event_bus.on(CrewKickoffStartedEvent)
        def on_crew_started(source, event):
            print(f"Crew '{event.crew_name}' started!")

my_listener = MyCustomListener()  # Automatically registers on init

# Use in a crew
crew = Crew(agents=[...], tasks=[...])
```

#### LlamaIndex

LlamaIndex uses callback managers with handlers.

Naming (Python): Callbacks (CallbackManager, BaseCallbackHandler)  
Supports: Y (read)  
Observation: Observer pattern with event methods for queries and tools; handlers can observe events/payloads (e.g., read prompts/responses) but are designed for debugging/tracing without modifying execution context.

For more details, see the official documentation: [Callbacks - LlamaIndex](https://docs.llamaindex.ai/en/stable/module_guides/observability/callbacks/). Here's an example setup (Python):

```python
from llama_index.core.callbacks import CallbackManager, LlamaDebugHandler

debug_handler = LlamaDebugHandler()  # Concrete handler subclassing BaseCallbackHandler
callback_manager = CallbackManager([debug_handler])

# Assign to components, e.g., an index or query engine
index = VectorStoreIndex.from_documents(documents, callback_manager=callback_manager)
query_engine = index.as_query_engine()
response = query_engine.query("What is this about?")
```

#### Haystack

Haystack does not support explicit middleware or filters like the others. Instead, it uses a modular pipeline architecture for interception via components (e.g., ConditionalRouter for routing based on conditions like tool calls) and observability through logging/tracing integrations (e.g., Langfuse).

Naming (Python): N/A (Pipeline Components/Routers)  
Supports: N (Pipeline-based interception)  
Observation: Relies on modular pipelines for implicit interception but lacks explicit middleware/filters; custom components can read/write data flow via routing/transformations, but this is compositional rather than hook-based interception.

For more details, see the official documentation: [Pipelines - Haystack Documentation](https://docs.haystack.deepset.ai/docs/pipelines). Here's an example of pipeline-based interception with a custom collector component (Python):

```python
from haystack import Pipeline
from haystack.components.generators.chat import OpenAIChatGenerator
from haystack.components.routers import ConditionalRouter
from haystack.components.tools import ToolInvoker
from haystack.tools import ComponentTool
from haystack.components.websearch import SerperDevWebSearch
from haystack.dataclasses import ChatMessage
from typing import Any, Dict, List
from haystack import component
from haystack.core.component.types import Variadic

# Custom component to collect/observe messages (for interception/observation)
@component()
class MessageCollector:
    def __init__(self):
        self._messages = []
    @component.output_types(messages=List[ChatMessage])
    def run(self, messages: Variadic[List[ChatMessage]]) -> Dict[str, Any]:
        self._messages.extend([msg for inner in messages for msg in inner])
        return {"messages": self._messages}
    def clear(self):
        self._messages = []

# Define a tool
web_tool = ComponentTool(component=SerperDevWebSearch(top_k=3))

# Define routes for filtering (e.g., check for tool calls)
routes = [
    {
        "condition": "{{replies[0].tool_calls | length > 0}}",
        "output": "{{replies}}",
        "output_name": "there_are_tool_calls",
        "output_type": List[ChatMessage],
    },
    {
        "condition": "{{replies[0].tool_calls | length == 0}}",
        "output": "{{replies}}",
        "output_name": "final_replies",
        "output_type": List[ChatMessage],
    },
]

# Build the pipeline
pipeline = Pipeline()
pipeline.add_component("generator", OpenAIChatGenerator(model="gpt-4o-mini"))
pipeline.add_component("router", ConditionalRouter(routes=routes))
pipeline.add_component("tool_invoker", ToolInvoker(tools=[web_tool]))
pipeline.add_component("message_collector", MessageCollector())

# Connect components (interception via routing and collection)
pipeline.connect("generator.replies", "router.replies")
pipeline.connect("router.there_are_tool_calls", "tool_invoker.messages")
pipeline.connect("tool_invoker.messages", "message_collector.messages")
pipeline.connect("router.final_replies", "message_collector.messages")

# Run the pipeline (observes via collector, filters via router)
result = pipeline.run({"generator": {"messages": [ChatMessage.from_user("What's the weather in Berlin?")]}})
print(result["message_collector"]["messages"])
```

#### OpenAI Swarm

OpenAI Swarm does not provide native support for middleware, filters, callbacks, or hooks. While interception can be achieved through custom implementations (e.g., function wrappers, client subclassing, or manual tool execution with `execute_tools=False`), this requires the caller to implement their own logic, which is not considered built-in framework support.

Naming (Python): N/A  
Supports: N  
Observation: No explicit middleware/filters; interception requires custom wrappers or manual handling (e.g., function decorators, client subclassing), lacking native framework support for built-in components to accept such modifications.

For more details, see the official GitHub repository: [OpenAI Swarm GitHub](https://github.com/openai/swarm). No native code examples available for interception; custom approaches are possible but not framework-native.

#### Atomic Agents

Atomic Agents does not support explicit middleware, callbacks, hooks, or filters. Its modularity allows composable components, but no dedicated interception mechanisms are documented.

Naming (Python): N/A (Composable Components)  
Supports: N  
Observation: No explicit middleware/filters; modularity allows composable units but no dedicated interception hooks or callbacks for custom reading/modification mid-execution.

For more details, see the official documentation: [Atomic Agents Docs](https://brainblend-ai.github.io/atomic-agents/). No specific code examples available for interception.

#### Smolagents (Hugging Face)

Smolagents does not support explicit middleware, callbacks, hooks, or filters; it focuses on simple agent building.

Naming (Python): N/A  
Supports: N  
Observation: No explicit support; focuses on simple agent building without interception mechanisms or hooks for reading/modifying execution.

For more details, see the official documentation: [Smolagents Docs](https://huggingface.co/docs/smolagents/en/index). No specific code examples available for interception.

#### Phidata (Agno)

Phidata (Agno) does not support explicit middleware, callbacks, hooks, or filters; agents rely on tools and memory.

Naming (Python): N/A  
Supports: N  
Observation: No explicit middleware/filters; agents use tools/memory but no interception hooks for custom reading/modification of calls.

For more details, see the official documentation: [Phidata Docs](https://docs.phidata.com/). No specific code examples available for interception.

#### PromptFlow (Microsoft)

PromptFlow supports tracing for LLM interactions, which acts like callbacks for debugging and iteration.

Naming (Python): Tracing  
Supports: N (Tracing only)  
Observation: Supports tracing for LLM interactions, acting as callbacks for debugging/iteration; tracing is read-only for observability/telemetry without options to modify context or intercept calls beyond logging.

For more details, see the official documentation: [Tracing in PromptFlow](https://microsoft.github.io/promptflow/how-to-guides/tracing/index.html). No direct code examples in the browsed content, but tracing is integrated into flow debugging (Python).

#### n8n

n8n's AI Agent node inherits callbacks from LangChain for observability in workflows.

Naming (JS/TS): Callbacks (inherited from LangChain)  
Supports: Y (read/write)  
Observation: AI Agent node uses LangChain under the hood, inheriting callbacks for observability; supports reading/modifying metadata or interrupting flow as in LangChain.

For more details, see the official documentation: [AI Agent Node Docs](https://docs.n8n.io/integrations/builtin/cluster-nodes/root-nodes/n8n-nodes-langchain.agent/). (Inherits from LangChain; refer to LangChain docs for callback examples.) No specific n8n-unique code in the content, but uses LangChain's observer pattern. Here's an adapted LangChain JS example for consistency:

```javascript
import { BaseCallbackHandler } from "@langchain/core/callbacks/base";

class MyHandler extends BaseCallbackHandler {
  name = "my_handler";

  async handleChainStart(chain, inputs) {
    inputs.number += 1;  # Modify inputs (write capability)
    console.log("Chain started!");
  }
}

const handler = new MyHandler();

// Pass callback at runtime
await chain.invoke({ number: 25 }, { callbacks: [handler] });

// Or at constructor time
const chainWithHandler = new SomeChain({ callbacks: [handler] });
await chainWithHandler.invoke({ number: 25 });
```
