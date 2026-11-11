// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Workflows.Observability;

/// <summary>
/// Configuration options for workflow telemetry.
/// </summary>
public sealed class WorkflowTelemetryOptions
{
    /// <summary>
    /// Gets or sets a legacy option that no longer affects workflow telemetry.
    /// </summary>
    /// <value>
    /// The value is ignored. The default value is <see langword="false"/>.
    /// </value>
    /// <remarks>
    /// Workflow payload attributes are no longer emitted. This option is deprecated
    /// and will be removed in version 1.30.0. Agent and chat-client payload capture settings are unaffected.
    /// </remarks>
    [Obsolete("Workflow payload attributes are no longer emitted. This option has no effect and will be removed in version 1.30.0.")]
    public bool EnableSensitiveData { get; set; }

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
    /// <see langword="true"/> to disable <c>invoke_workflow {gen_ai.workflow.name}</c> activities
    /// (or <c>invoke_workflow</c> when unnamed);
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
