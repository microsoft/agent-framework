// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;

namespace Microsoft.Agents.AI.DurableTask.Workflows;

/// <summary>
/// Provides centralized OpenTelemetry instrumentation for durable workflow execution.
/// </summary>
internal static class DurableWorkflowInstrumentation
{
    /// <summary>
    /// The shared <see cref="ActivitySource"/> used by all durable workflow components.
    /// </summary>
    internal static readonly ActivitySource ActivitySource = new("Microsoft.Agents.AI.DurableTask.Workflows");

    /// <summary>
    /// Carries the W3C traceparent of the client-side workflow.run span through the
    /// orchestrator's async call chain so it can be included in activity inputs.
    /// </summary>
    internal static readonly AsyncLocal<string?> WorkflowRunTraceParent = new();
}
