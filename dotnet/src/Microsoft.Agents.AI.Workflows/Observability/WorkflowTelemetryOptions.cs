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

    /// <summary>
    /// Gets or sets a value indicating whether an <see cref="AIAgent"/>-hosted workflow execution
    /// should preserve sensitive data on generic workflow spans.
    /// </summary>
    /// <value>
    /// <see langword="true"/> to allow workflows in the hosted execution to emit raw executor inputs,
    /// executor outputs, and message content according to their <see cref="EnableSensitiveData"/> settings;
    /// otherwise, <see langword="false"/> to suppress those generic payload tags. The default is
    /// <see langword="false"/>.
    /// </value>
    /// <remarks>
    /// Agent, model, and tool instrumentation can emit the same content under canonical GenAI
    /// attributes. Suppressing the generic workflow copies by default avoids duplicating sensitive
    /// content under <c>executor.input</c>, <c>executor.output</c>, and <c>message.content</c>.
    /// Configure this option on the outermost workflow passed to <c>AsAIAgent</c>. Suppression applies
    /// to nested workflows and nested hosted workflow agents and cannot be overridden by an inner workflow.
    /// </remarks>
    public bool IncludeSensitiveDataWhenHostedAsAgent { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether workflow build activities should be disabled.
    /// </summary>
    /// <value>
    /// <see langword="true"/> to disable <c>workflow.build</c> activities;
    /// <see langword="false"/> to enable them. The default value is <see langword="false"/>.
    /// </value>
    public bool DisableWorkflowBuild { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether workflow run activities should be disabled.
    /// </summary>
    /// <value>
    /// <see langword="true"/> to disable <c>workflow_invoke</c> activities;
    /// <see langword="false"/> to enable them. The default value is <see langword="false"/>.
    /// </value>
    public bool DisableWorkflowRun { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether executor process activities should be disabled.
    /// </summary>
    /// <value>
    /// <see langword="true"/> to disable <c>executor.process</c> activities;
    /// <see langword="false"/> to enable them. The default value is <see langword="false"/>.
    /// </value>
    public bool DisableExecutorProcess { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether edge group process activities should be disabled.
    /// </summary>
    /// <value>
    /// <see langword="true"/> to disable <c>edge_group.process</c> activities;
    /// <see langword="false"/> to enable them. The default value is <see langword="false"/>.
    /// </value>
    public bool DisableEdgeGroupProcess { get; set; }

    /// <summary>
    /// Gets or sets a value indicating whether message send activities should be disabled.
    /// </summary>
    /// <value>
    /// <see langword="true"/> to disable <c>message.send</c> activities;
    /// <see langword="false"/> to enable them. The default value is <see langword="false"/>.
    /// </value>
    public bool DisableMessageSend { get; set; }
}
