// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a mechanism for injecting messages into an agent run, while the agent is executing, where an agent supports this behavior.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public interface IChatMessageInjector
{
    /// <summary>
    /// Enqueues one or more messages to be used at the next opportunity.
    /// </summary>
    /// <remarks>
    /// This method is thread-safe and can be called concurrently from tool delegates or other code
    /// while the function execution loop is in progress. The enqueued messages will be picked up
    /// at the next opportunity.
    /// </remarks>
    /// <param name="messages">The messages to enqueue.</param>
    void EnqueueMessages(IEnumerable<ChatMessage> messages);
}
