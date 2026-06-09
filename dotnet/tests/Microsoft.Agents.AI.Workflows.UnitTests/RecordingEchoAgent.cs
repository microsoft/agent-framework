// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

/// <summary>
/// A <see cref="TestEchoAgent"/> that records the input messages it receives on each call.
/// Used by tests that need to assert what context a participant was actually handed - for example,
/// that a later speaker sees prior participants' <em>responses</em> (the running conversation) rather
/// than their <em>instructions</em>.
/// </summary>
internal sealed class RecordingEchoAgent(string? id = null, string? name = null, string? prefix = null)
    : TestEchoAgent(id, name, prefix)
{
    public List<List<ChatMessage>> RecordedInputs { get; } = [];

    protected override async IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(
        IEnumerable<ChatMessage> messages,
        AgentSession? session = null,
        AgentRunOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        // Materialize once so the deferred input is recorded and replayed identically.
        List<ChatMessage> recorded = messages.ToList();
        this.RecordedInputs.Add(recorded);

        await foreach (AgentResponseUpdate update in base.RunCoreStreamingAsync(recorded, session, options, cancellationToken))
        {
            yield return update;
        }
    }
}
