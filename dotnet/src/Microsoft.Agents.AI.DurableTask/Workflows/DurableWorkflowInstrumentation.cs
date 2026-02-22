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
}
