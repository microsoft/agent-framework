// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Orchestration;

/// <summary>
/// Common messages used by the <see cref="ConcurrentOrchestration{TInput, TOutput}"/>.
/// </summary>
internal static class ConcurrentMessages
{
    /// <summary>
    /// The input task for a <see cref="ConcurrentOrchestration{TInput, TOutput}"/>.
    /// </summary>
    public sealed record Request(IList<ChatMessage> Messages);

    /// <summary>
    /// A result from a <see cref="ConcurrentOrchestration{TInput, TOutput}"/>.
    /// </summary>
    public sealed record Result(ChatMessage Message);
}
