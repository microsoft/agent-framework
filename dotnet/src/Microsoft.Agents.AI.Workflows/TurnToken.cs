// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>
/// Sent to an <see cref="AIAgent"/>-based executor to request
/// a response to accumulated <see cref="ChatMessage"/>.
/// </summary>
public class TurnToken
{
    /// <summary>
    /// Initializes a new instance of the <see cref="TurnToken"/> class.
    /// </summary>
    /// <param name="emitEvents">Whether to raise agent run events for the receiving executor.</param>
    [JsonConstructor]
    public TurnToken(bool? emitEvents = null)
    {
        this.EmitEvents = emitEvents;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="TurnToken"/> class.
    /// </summary>
    /// <param name="emitEvents">Whether to raise agent run events for the receiving executor.</param>
    /// <param name="runOptions">Options to pass to agents invoked during this turn.</param>
    public TurnToken(bool? emitEvents, AgentRunOptions? runOptions)
        : this(emitEvents)
    {
        this.RunOptions = runOptions;
    }

    /// <summary>
    /// Gets a value indicating whether events are emitted by the receiving executor. If the
    /// value is not set, defaults to the configuration in the executor.
    /// </summary>
    public bool? EmitEvents { get; }

    /// <summary>
    /// Gets the options to pass to agents invoked during this turn.
    /// </summary>
    /// <remarks>
    /// Run options apply only to the current invocation and are not persisted in workflow checkpoints.
    /// </remarks>
    [JsonIgnore]
    public AgentRunOptions? RunOptions { get; }
}
