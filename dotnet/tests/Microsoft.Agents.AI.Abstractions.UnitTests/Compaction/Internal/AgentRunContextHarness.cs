// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Compaction.Internal;

/// <summary>
/// Provides a way to set <see cref="AIAgent.CurrentRunContext"/> in unit tests
/// so that the underlying <c>AsyncLocal</c> is populated for code that reads it.
/// </summary>
internal static class AgentRunContextHarness
{
    private static readonly ContextAgentShim s_instance = new();

    /// <summary>
    /// Sets <see cref="AIAgent.CurrentRunContext"/> and invokes the provided action.
    /// </summary>
    public static void ExecuteWithRunContext(AgentRunContext context, Action action)
    {
        Assert.NotNull(context);
        Assert.NotNull(action);
        //AgentRunContext context = new(agent, session, messages ?? [], options); // %%% TODO
        s_instance.Set(context);
        action.Invoke();
    }

    // Derived class that exposes the protected setter.
    private sealed class ContextAgentShim : AIAgent
    {
        public void Set(AgentRunContext? value) => CurrentRunContext = value;

        protected override ValueTask<AgentSession> CreateSessionCoreAsync(CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override ValueTask<JsonElement> SerializeSessionCoreAsync(AgentSession session, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override ValueTask<AgentSession> DeserializeSessionCoreAsync(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override Task<AgentResponse> RunCoreAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();

        protected override IAsyncEnumerable<AgentResponseUpdate> RunCoreStreamingAsync(IEnumerable<ChatMessage> messages, AgentSession? session = null, AgentRunOptions? options = null, CancellationToken cancellationToken = default)
            => throw new NotSupportedException();
    }
}
