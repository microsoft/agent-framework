---
status: proposed
contact: rogerbarreto
date: 2025-07-14
deciders: stephentoub, markwallace-microsoft, rogerbarreto, westey-m
informed: {}
---

# Agent OpenTelemetry Instrumentation

## Context and Problem Statement

Currently, the Agent Framework lacks comprehensive observability and telemetry capabilities, making it difficult for developers to monitor agent performance, track usage patterns, debug issues, and gain insights into agent behavior in production environments. While the underlying ChatClient implementations may have their own telemetry, there is no standardized way to capture agent-specific metrics and traces that provide visibility into agent operations, token usage, response times, and error patterns at the agent abstraction level.

## Decision Drivers

- **Compliance**: The implementation should adhere to established OpenTelemetry semantic conventions for agents, ensuring consistency and interoperability with existing telemetry systems.
- **Observability Requirements**: Developers need comprehensive telemetry to monitor agent performance, track usage patterns, and debug issues in production environments.
- **Standardization**: The solution must follow established OpenTelemetry semantic conventions and integrate seamlessly with existing .NET telemetry infrastructure.
- **Microsoft.Extensions.AI Alignment**: The implementation should follow the exact patterns and conventions established by Microsoft.Extensions.AI's OpenTelemetry instrumentation.
- **Non-Intrusive Design**: Telemetry should be optional and not impact the core agent functionality or performance when disabled.
- **Agent-Level Insights**: The telemetry should capture agent-specific operations without duplicating underlying ChatClient telemetry.
- **Extensibility**: The solution should support future enhancements and additional telemetry scenarios.

## Considered Options

### Option 1: Direct Integration into Core Agent Classes

Embed OpenTelemetry instrumentation directly into the base `Agent` class and `ChatClientAgent` implementations.

#### Pros
- Automatic telemetry for all agent implementations
- No additional wrapper classes needed
- Consistent telemetry across all agents

#### Cons
- Violates single responsibility principle
- Increases complexity of core agent classes
- Makes telemetry mandatory rather than optional
- Harder to test and maintain
- Couples telemetry concerns with business logic

### Option 2: Aspect-Oriented Programming (AOP) Approach

Use interceptors or AOP frameworks to inject telemetry behavior into agent methods.

#### Pros
- Clean separation of concerns
- Non-intrusive to existing code
- Can be applied selectively

#### Cons
- Adds complexity with AOP framework dependencies
- Runtime overhead for interception
- Harder to debug and understand
- Not consistent with Microsoft.Extensions.AI patterns

### Option 3: OpenTelemetryAgent Wrapper Pattern

Create a delegating `OpenTelemetryAgent` wrapper class that implements the `Agent` interface and wraps any existing agent with telemetry instrumentation, following the exact pattern of Microsoft.Extensions.AI's `OpenTelemetryChatClient`.

#### Pros
- Follows established Microsoft.Extensions.AI patterns exactly
- Clean separation of concerns
- Optional and non-intrusive
- Easy to test and maintain
- Consistent with .NET telemetry conventions
- Supports any agent implementation
- Provides agent-level telemetry without duplicating ChatClient telemetry

#### Cons
- Requires explicit wrapping of agents
- Additional object allocation for wrapper

## Decision Outcome

Chosen option: "OpenTelemetryAgent Wrapper Pattern", because it follows the established Microsoft.Extensions.AI patterns exactly, provides clean separation of concerns, maintains optional telemetry, and offers the best balance of functionality, maintainability, and consistency with existing .NET telemetry infrastructure.

### Implementation Details

The implementation includes:

1. **OpenTelemetryAgent Wrapper Class**: A delegating agent that wraps any `Agent` implementation with telemetry instrumentation
2. **AgentOpenTelemetryConsts**: Comprehensive constants for telemetry attribute names and metric definitions
3. **Extension Methods**: `.WithOpenTelemetry()` extension method for easy agent wrapping
4. **Comprehensive Test Suite**: Full test coverage following Microsoft.Extensions.AI testing patterns

### Telemetry Data Captured

**Activities/Spans:**
- `agent.operation.name` (agent.run, agent.run_streaming)
- `agent.request.id`, `agent.request.name`, `agent.request.instructions`
- `agent.request.message_count`, `agent.request.thread_id`
- `agent.response.id`, `agent.response.message_count`, `agent.response.finish_reason`
- `agent.usage.input_tokens`, `agent.usage.output_tokens`
- Error information and activity status codes

**Metrics:**
- Operation duration histogram with proper buckets
- Token usage histogram (input/output tokens)
- Request count counter
- All metrics tagged with operation type and agent name

### Consequences

- **Good**: Provides comprehensive agent-level observability following established patterns
- **Good**: Non-intrusive and optional implementation that doesn't affect core functionality
- **Good**: Consistent with Microsoft.Extensions.AI telemetry conventions
- **Good**: Easy to integrate with existing OpenTelemetry infrastructure
- **Good**: Supports debugging, monitoring, and performance analysis
- **Neutral**: Requires explicit wrapping of agents with `.WithOpenTelemetry()`
- **Neutral**: Additional object allocation for telemetry wrapper

## Validation

The implementation is validated through:

1. **Comprehensive Unit Tests**: 16 test methods covering all scenarios including success, error, streaming, and edge cases
2. **Integration Testing**: Step05 telemetry sample demonstrating real-world usage
3. **Pattern Compliance**: Exact adherence to Microsoft.Extensions.AI OpenTelemetry patterns
4. **Semantic Convention Compliance**: Follows OpenTelemetry semantic conventions for telemetry data

## More Information

### Usage Example

```csharp
// Create TracerProvider
using var tracerProvider = Sdk.CreateTracerProviderBuilder()
    .AddSource(AgentOpenTelemetryConsts.DefaultSourceName)
    .AddConsoleExporter()
    .Build();

// Create and wrap agent with telemetry
var baseAgent = new ChatClientAgent(chatClient, options);
using var telemetryAgent = baseAgent.WithOpenTelemetry();

// Use agent normally - telemetry is captured automatically
var response = await telemetryAgent.RunAsync(messages);
```

### Relationship to Microsoft.Extensions.AI

This implementation follows the exact patterns established by Microsoft.Extensions.AI's OpenTelemetry instrumentation, ensuring consistency across the AI ecosystem and leveraging proven patterns for telemetry integration.
