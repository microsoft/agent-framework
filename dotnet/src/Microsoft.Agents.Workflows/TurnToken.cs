// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows;

/// <summary>
/// Sent to an <see cref="AIAgent"/>-based executor to request
/// a response to accumulated <see cref="Extensions.AI.ChatMessage"/>.
/// </summary>
/// <param name="emitEvents">Whether to raise AgentRunEvents for this executor.</param>
public class TurnToken(bool? emitEvents = null)
{
    /// <summary>
    /// Gets a value indicating whether events are emitted by the receiving executor. If the
    /// value is not set, defaults to the configuration in the executor.
    /// </summary>
    public bool? EmitEvents => emitEvents;
}
