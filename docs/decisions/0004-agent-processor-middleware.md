---
status: proposed
contact: rogerbarreto
date: 2025-08-14
deciders: stephentoub, markwallace-microsoft, rogerbarreto, westey-m
informed: {}
---

# Agent Processor Middleware Architecture

## Context and Problem Statement

The current Agent Framework lacks a standardized, extensible mechanism for intercepting and processing agent execution at various stages of the lifecycle. Developers need the ability to implement cross-cutting concerns such as logging, validation, caching, rate limiting, approval workflows, and error handling without modifying core agent implementations. While the framework has basic agent abstractions with `RunAsync` and `RunStreamingAsync` methods, there is no middleware-like pipeline that allows for composable, reusable processing components that can be applied to different agent execution contexts.

The challenge is to design an architecture that supports:
- Multiple execution contexts (pre-invocation, function calls, approval requests, post-execution, error handling)
- Both streaming and non-streaming scenarios
- Composable middleware-like behavior with proper chaining
- Self-registering processors that declare their supported contexts
- Manual setup (without DI) and dependency injection scenarios
- True middleware behavior where post-`next()` logic executes after core agent logic

## Decision Drivers

- **Extensibility**: Enable developers to add custom processing logic without modifying core agent implementations
- **Composability**: Support chaining multiple processors in a pipeline with proper middleware semantics
- **Context Awareness**: Different processors should handle specific execution contexts (pre-invocation, function calls, etc.)
- **Streaming Support**: Architecture must work seamlessly with both `RunAsync` and `RunStreamingAsync` scenarios
- **Self-Registration**: Processors should declare their supported contexts to reduce configuration errors
- **Middleware Semantics**: Post-`next()` code should execute after core agent logic, not before
- **Flexibility**: Support both manual configuration and dependency injection patterns
- **Performance**: Minimal overhead when processors are not registered for specific contexts
- **Immutability**: Maintain clear data flow with explicit context mutations
- **Testability**: Enable easy unit testing of individual processors and processor chains

## Considered Options

### Option 1: Event-Based Architecture
Implement an event-driven system where agents raise events at different execution stages, and handlers subscribe to specific event types.

#### Pros
- Loose coupling between agents and processors
- Easy to add new event types
- Familiar pattern for many developers
- Natural support for multiple handlers per event

#### Cons
- Events are fire-and-forget, making it difficult to modify execution flow
- No natural way to short-circuit execution or return modified contexts
- Complex error handling and rollback scenarios
- Difficult to maintain execution order and dependencies
- Does not provide true middleware semantics

### Option 2: Decorator Pattern with Agent Wrappers
Create decorator classes that wrap agents and intercept method calls, similar to the OpenTelemetryAgent pattern.

#### Pros
- Clean separation of concerns
- Follows established patterns in the framework
- Easy to compose multiple decorators
- Non-intrusive to existing agent implementations

#### Cons
- Limited to agent-level interception only
- Cannot intercept fine-grained execution contexts (function calls, approval requests)
- Requires creating multiple wrapper classes for different concerns
- Does not support context-specific processing
- Difficult to share processors across different agent types

### Option 3: Processor Middleware Architecture (Recommended)
Implement a middleware-like pipeline using processor interfaces that handle specific execution contexts, with a dispatcher that manages processor chains and supports both manual and DI configuration.

#### Pros
- True middleware semantics with proper pre/post execution logic
- Context-specific processing with self-registering processors
- Supports both streaming and non-streaming scenarios
- Composable and reusable processor components
- Clean separation between processor logic and agent implementation
- Flexible configuration options (manual and DI)
- Explicit context mutations with immutable data flow
- Easy to test individual processors and chains

#### Cons
- More complex initial setup compared to simple event handlers
- Requires understanding of middleware concepts
- Additional abstraction layer between agents and processing logic

## Decision Outcome

Chosen option: "Processor Middleware Architecture", because it provides the best balance of flexibility, composability, and middleware semantics while supporting all required execution contexts and scenarios. This approach enables true middleware behavior where processors can execute logic both before and after core agent operations, supports self-registering processors to reduce configuration errors, and works seamlessly with both streaming and non-streaming agent execution.

### Implementation Overview

The architecture consists of:

1. **AgentContext Hierarchy**: Base context class with specialized contexts for different execution stages
2. **IAgentContextProcessor Interface**: Processors that declare supported contexts and implement middleware logic
3. **AgentMiddlewareProcessor Dispatcher**: Manages processor registration and chain execution
4. **AIAgent Integration**: Modified base agent class that integrates with the processor pipeline

### Key Components

#### Context Types and Classes
```csharp
public abstract class AgentContext
{
    public AgentContextType ContextType { get; }
    public bool IsStreaming { get; }
}

public sealed class RunAgentContext : AgentContext
{
    public AgentRunOptions Options { get; }
    public AgentThread? Thread { get; }
}
```

#### Processor Interface
```csharp
public interface IAgentMiddleware
{
    bool CanProcess(Type contextType);
    Task<AgentContext> ProcessAsync(AgentContext context, AgentContextProcessorDelegate next);
}
```

#### Middleware Processor
```csharp
public class AgentMiddlewareProcessor
{
    // Keep processors organized by context type
    Dictionary<string, AgentContext> _contextByType = new();

    // Register processors via ctor/DI
    public AgentMiddlewareProcessor(IEnumerable<IAgentMiddleware> middlewares) { } 

    // Manual registration for non-DI scenarios
    public void Register(IAgentMiddleware middleware) 
    { 
        _contextByType.CanProcess(typeof(RunAgentContext)).Add(nameof(RunAgentContext),middleware);
    }

    // Execute the processor chain
    public Task<AgentContext> ProcessChainAsync(AgentContext context, Func<AgentContext, Task<AgentContext>> next) 
    {
        // Iterate through processors registered for the given context type
        foreach (var middleware in _contextByType[context.GetType().Name])
        {
            context = await middleware.ProcessAsync(context, next).ConfigureAwait(false);
        }
        return context;
    }
}
```

#### AIAgent Middleware Wrapper
```csharp
public class AIAgent
{
    public AIAgent(AgentMiddlewareProcessor? processor = null) { }

    public virtual Task<AgentResponse> RunAsync(AgentRunOptions options, AgentThread? thread = null)
    {
        // Wrap core logic in middleware pipeline
        return _processor.ProcessChainAsync(new RunAgentContext(options, thread), context =>
        {
            // Core agent logic
            return Task.FromResult(context);
        });
    }
}
```

### Consequences

- **Good**: Provides comprehensive middleware pipeline for agent execution with proper semantics
- **Good**: Self-registering processors reduce configuration errors and improve developer experience
- **Good**: Supports both manual setup and dependency injection patterns
- **Good**: Context-specific processing enables fine-grained control over agent execution
- **Good**: Immutable context updates provide clear data flow and easier debugging
- **Good**: Composable architecture allows mixing and matching processors for different scenarios
- **Good**: Streaming and non-streaming scenarios handled uniformly
- **Neutral**: Requires understanding of middleware concepts and processor patterns
- **Neutral**: Additional abstraction layer adds some complexity to simple agent scenarios
- **Bad**: Initial setup is more complex than simple event-based approaches

## Validation

The implementation will be validated through:

1. **Unit Tests**: Comprehensive test suite covering individual processors, chain execution, and edge cases
2. **Integration Tests**: End-to-end scenarios with real agents and multiple processors
3. **Performance Tests**: Benchmarks to ensure minimal overhead when processors are not registered
4. **Sample Applications**: Demonstration of common use cases including logging, validation, caching, and rate limiting
5. **Documentation**: Complete API documentation and usage examples for both manual and DI scenarios

## More Information

### Usage Examples

#### Manual Setup
```csharp
var processor = new AgentMiddlewareProcessor();
processor.Register([new AgentOptionsProcessor(), new ValidationProcessor(), new ContentSafetyProcessor()]);

AIAgent agent = GetAgent().WithMiddleware(processor);
var response = await agent.RunAsync(messages);
```

#### Dependency Injection Setup
```csharp
builder.Services.AddSingleton<IAgentMiddleware, AgentOptionsProcessor>();
builder.Services.AddSingleton<IAgentMiddleware, ValidationProcessor>();
builder.Services.AddSingleton<IAgentMiddleware, ContentSafetyProcessor>();
builder.Services.AddSingleton<AgentMiddlewareProcessor>();
builder.Services.AddSingleton<AIAgent>(sp => {
    var agent = GetAgent();
    agent.AddMiddleware(sp.GetRequiredService<AgentMiddlewareProcessor>());
    return agent;
});
```

### Relationship to Existing Architecture

This middleware architecture complements the existing agent framework by:
- Building on the established `AIAgent` abstract class
- Working with existing `RunAsync` and `RunStreamingAsync` patterns
- Integrating with the OpenTelemetry instrumentation (ADR-0002)
- Providing the foundation for the agent filters functionality (ADR-0003)

### Future Considerations

- Integration with actor runtime for distributed scenarios
- Support for async processor registration and dynamic processor loading
- Enhanced error handling and recovery mechanisms
- Performance optimizations for high-throughput scenarios
