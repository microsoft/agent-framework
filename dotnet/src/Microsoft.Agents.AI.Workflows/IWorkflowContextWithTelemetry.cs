// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Observability;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Internal interface that extends IWorkflowContext to provide access to telemetry context.
/// </summary>
internal interface IWorkflowContextWithTelemetry : IWorkflowContext
{
    /// <summary>
    /// Gets the telemetry context for the workflow.
    /// </summary>
    WorkflowTelemetryContext TelemetryContext { get; }
}
