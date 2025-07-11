// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// A message that describes the input task and captures results for a <see cref="HandoffOrchestration{TInput,TOutput}"/>.
/// </summary>
internal static class HandoffMessages
{
    /// <summary>
    /// The input message.
    /// </summary>
    public sealed record InputTask(IList<ChatMessage> Messages);

    /// <summary>
    /// The final result.
    /// </summary>
    public sealed record Result(ChatMessage Message);

    /// <summary>
    /// Signals the handoff to another agent.
    /// </summary>
    public sealed class Request;

    /// <summary>
    /// Broadcast an agent response to all actors in the orchestration.
    /// </summary>
    public sealed record Response(ChatMessage Message);
}
