// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.Workflows.Observability;

/// <summary>
/// Configuration options for workflow telemetry.
/// </summary>
public sealed class WorkflowTelemetryOptions
{
    /// <summary>
    /// Gets or sets a value indicating whether potentially sensitive information should be included in telemetry.
    /// </summary>
    /// <value>
    /// <see langword="true"/> if potentially sensitive information should be included in telemetry;
    /// <see langword="false"/> if telemetry shouldn't include raw inputs and outputs.
    /// The default value is <see langword="false"/>.
    /// </value>
    /// <remarks>
    /// By default, telemetry includes metadata but not raw inputs and outputs,
    /// such as message content and executor data.
    /// </remarks>
    public bool EnableSensitiveData { get; set; }
}
