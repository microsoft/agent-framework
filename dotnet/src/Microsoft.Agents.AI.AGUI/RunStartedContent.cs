// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Represents content indicating that an agent run has started.
/// </summary>
public sealed class RunStartedContent : AIContent
{
    /// <summary>
    /// Initializes a new instance of the <see cref="RunStartedContent"/> class.
    /// </summary>
    /// <param name="threadId">The ID of the conversation thread.</param>
    /// <param name="runId">The ID of the agent run.</param>
    public RunStartedContent(string threadId, string runId)
    {
        this.ThreadId = threadId;
        this.RunId = runId;
    }

    /// <summary>
    /// Gets the ID of the conversation thread.
    /// </summary>
    public string ThreadId { get; }

    /// <summary>
    /// Gets the ID of the agent run.
    /// </summary>
    public string RunId { get; }
}
