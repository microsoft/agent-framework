// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ComponentModel;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI;
using Microsoft.Extensions.Logging;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Represents the result of an orchestrating agent.
/// This class encapsulates the asynchronous completion of an orchestration process.
/// </summary>
public sealed partial class OrchestratingAgentResponse : IAsyncDisposable
{
    private readonly CancellationTokenSource _cancelSource;
    private readonly ILogger _logger;

    internal OrchestratingAgentResponse(
        OrchestratingAgentContext context,
        Task<AgentRunResponse> completion,
        CancellationTokenSource orchestrationCancelSource,
        ILogger logger)
    {
        this.Context = context;
        this._cancelSource = orchestrationCancelSource;
        this.Task = completion;
        this._logger = logger;
    }

    /// <summary>Gets the <see cref="OrchestratingAgentContext"/> associated with this response.</summary>
    public OrchestratingAgentContext Context { get; }

    /// <summary>
    /// Releases all resources used by the <see cref="OrchestratingAgentResponse"/> instance.
    /// </summary>
    public ValueTask DisposeAsync()
    {
        this._cancelSource.Dispose();
        return default;
    }

    /// <summary>
    /// Gets a task that represents the completion of the orchestration result.
    /// </summary>
    public Task<AgentRunResponse> Task { get; }

    /// <summary>
    /// Requests cancellation of the orchestration associated with this result.
    /// </summary>
    /// <exception cref="ObjectDisposedException">Thrown if this instance has been disposed.</exception>
    public void Cancel()
    {
        OrchestratingAgent.LogOrchestrationCancellationRequested(this._logger, this.Context.ToString(), this.Context.Id);
        this._cancelSource.Cancel();
    }

    /// <summary>Enable directly awaiting an <see cref="OrchestratingAgentResponse"/> by using <see cref="Task"/>'s awaiter.</summary>
    [EditorBrowsable(EditorBrowsableState.Never)]
    public TaskAwaiter<AgentRunResponse> GetAwaiter() => this.Task.GetAwaiter();
}
