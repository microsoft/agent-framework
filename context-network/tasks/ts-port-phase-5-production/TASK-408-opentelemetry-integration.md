# Task: TASK-408 OpenTelemetry Integration

**Phase**: 5
**Priority**: High
**Estimated Effort**: 6 hours
**Dependencies**: TASK-007 (BaseAgent), TASK-101 (ChatAgent), TASK-302 (Workflow Executor)

### Objective
Implement OpenTelemetry integration for distributed tracing, metrics, and observability across agents and workflows.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-10 (Observability)
- **Python Reference**: `/python/packages/core/agent_framework/telemetry.py`
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI/Telemetry/`
- **Standards**: CLAUDE.md § Python Architecture → OpenTelemetry

### Files to Create/Modify
- `src/telemetry/configure.ts` - Telemetry configuration
- `src/telemetry/decorators.ts` - @traced decorator
- `src/telemetry/spans.ts` - Span utilities
- `src/telemetry/__tests__/telemetry.test.ts` - Tests
- `src/index.ts` - Exports

### Implementation Requirements

**Core Functionality**:
1. Implement telemetry configuration function
2. Create tracer provider setup
3. Create meter provider setup
4. Implement @traced decorator for automatic tracing
5. Create span helpers for agent invocations
6. Create span helpers for tool executions
7. Create span helpers for workflow execution
8. Record metrics (token usage, latency, errors)
9. Support trace context propagation
10. Support custom attributes and metadata

**Test Requirements**: Unit tests for configuration, decorators, span creation, metrics recording

**Acceptance Criteria**: OpenTelemetry working, spans created, metrics recorded, trace propagation

### Example Code Pattern
```typescript
import { trace, metrics, SpanStatusCode } from '@opentelemetry/api';

export const telemetry = {
  configure(options: TelemetryOptions): void {
    // Setup tracer provider
    // Setup meter provider
    // Register instrumentation
  },

  getTracer(name?: string): Tracer {
    return trace.getTracer(name ?? '@microsoft/agent-framework');
  },

  getMeter(name?: string): Meter {
    return metrics.getMeter(name ?? '@microsoft/agent-framework');
  }
};

export function traced(spanName?: string) {
  return function (
    target: any,
    propertyKey: string,
    descriptor: PropertyDescriptor
  ) {
    const originalMethod = descriptor.value;

    descriptor.value = async function (...args: any[]) {
      const tracer = telemetry.getTracer();
      return await tracer.startActiveSpan(
        spanName ?? `${target.constructor.name}.${propertyKey}`,
        async (span) => {
          try {
            const result = await originalMethod.apply(this, args);
            span.setStatus({ code: SpanStatusCode.OK });
            return result;
          } catch (error) {
            span.recordException(error as Error);
            span.setStatus({ code: SpanStatusCode.ERROR });
            throw error;
          } finally {
            span.end();
          }
        }
      );
    };

    return descriptor;
  };
}
```

### Related Tasks
- **Blocked by**: TASK-007 (BaseAgent for instrumentation)
- **Blocked by**: TASK-101 (ChatAgent for instrumentation)
- **Related**: TASK-401 (A2A needs trace propagation)
- **Related**: TASK-302 (Workflows need tracing)
