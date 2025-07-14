// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// A message that describes the input task and captures results for a <see cref="SequentialOrchestration{TInput,TOutput}"/>.
/// </summary>
internal static class SequentialMessages
{
    /// <summary>
    /// Represents a request containing a sequence of chat messages to be processed by the sequential orchestration.
    /// </summary>
    public sealed record Request(IList<ChatMessage> Messages);

    /// <summary>
    /// Represents a response containing the result message from the sequential orchestration.
    /// </summary>
    public sealed record Response(ChatMessage Message);
}
