// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Extensions.AI.Agents.Runtime;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Logging.Abstractions;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Provides contextual information for an orchestration operation, including logging, and response callback.
/// </summary>
public sealed class OrchestratingAgentContext
{
    private ILogger? _logger;
    private string? _id;

    /// <summary>Gets the orchestrating agent associated with this operation.</summary>
    public OrchestratingAgent? OrchestratingAgent { get; set; }

    /// <summary>Gets the associated agent runtime, if one is being used.</summary>
    public IActorRuntimeContext? Runtime { get; set; }

    /// <summary>Gets the options associated with the orchestration run.</summary>
    public AgentRunOptions? Options { get; set; }

    /// <summary>Gets or sets the last version number provided by the runtime for checkpoint state.</summary>
    public string? ETag { get; set; }

    /// <summary>Gets or sets an ID to use for the orchestration operation.</summary>
    public string Id
    {
        get
        {
            this._id ??= this.Runtime?.ActorId.ToString() ?? Guid.NewGuid().ToString("N");
            return this._id;
        }
    }

    /// <summary>
    /// Gets the associated logger for this operation.
    /// </summary>
    public ILogger Logger
    {
        get => this._logger ?? NullLogger.Instance;
        set => this._logger = value;
    }

    /// <inheritdoc />
    public override string ToString() =>
        this.OrchestratingAgent?.DisplayName ??
        nameof(OrchestratingAgentContext);
}
