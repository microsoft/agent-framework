// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// A <see cref="TestReplayAgent"/> that records the input messages it receives on each call.
/// Used by tests that need to assert what context the agent was actually handed.
/// </summary>
internal sealed class RecordingReplayAgent(List<List<ChatMessage>> messages, string? id = null, string? name = null)
    : TestReplayAgent(messages, id, name)
{
    public List<List<ChatMessage>> RecordedInputs { get; } = [];

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        this.RecordedInputs.Add(messages.ToList());
        await foreach (AgentResponseUpdate update in base.RunCoreStreamingAsync(messages, session, options, cancellationToken))
        {
            yield return update;
        }
    }
}
