// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Represents content indicating that an agent run has finished successfully.
/// </summary>
public sealed class RunFinishedContent : AIContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="RunFinishedContent"/> class.
    /// </summary>
    /// <param name="threadId">The ID of the conversation thread.</param>
    /// <param name="runId">The ID of the agent run.</param>
    /// <param name="result">Optional result data from the run.</param>
    public RunFinishedContent(string threadId, string runId, string? result)
    {
        this.ThreadId = threadId;
        this.RunId = runId;
        this.Result = result;
    }

    /// <summary>
    /// Gets the ID of the conversation thread.
    /// </summary>
    public string ThreadId { get; }

    /// <summary>
    /// Gets the ID of the agent run.
    /// </summary>
    public string RunId { get; }

    /// <summary>
    /// Gets optional result data from the run.
    /// </summary>
    public string? Result { get; }
}
