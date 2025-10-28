// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AGUI;

/// <summary>
/// Provides an <see cref="AgentThread"/> implementation for AG-UI agents.
/// </summary>
internal sealed class AGUIAgentThread : InMemoryAgentThread
{
    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIAgentThread"/> class.
    /// </summary>
    public AGUIAgentThread()
        : base()
    {
        this.ThreadId = Guid.NewGuid().ToString();
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AGUIAgentThread"/> class from serialized state.
    /// </summary>
    /// <param name="serializedThreadState">The serialized thread state.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serializer options.</param>
    public AGUIAgentThread(JsonElement serializedThreadState, JsonSerializerOptions? jsonSerializerOptions = null)
        : base(UnwrapState(serializedThreadState), jsonSerializerOptions)
    {
        var threadId = serializedThreadState.TryGetProperty(nameof(AGUIAgentThreadState.ThreadId), out var stateElement)
            ? stateElement.GetString()
            : null;

        if (string.IsNullOrEmpty(threadId))
        {
            Throw.InvalidOperationException("Serialized thread is missing required ThreadId.");
        }
        this.ThreadId = threadId;
    }

    private static JsonElement UnwrapState(JsonElement serializedThreadState)
    {
        var state = serializedThreadState.Deserialize(AGUIJsonSerializerContext.Default.AGUIAgentThreadState);
        if (state == null)
        {
            Throw.InvalidOperationException("Serialized thread is missing required WrappedState.");
        }

        return state.WrappedState;
    }

    /// <summary>
    /// The ID associated with this thread.
    /// </summary>
    public string ThreadId { get; set; }

    /// <inheritdoc/>
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var wrappedState = base.Serialize(jsonSerializerOptions);
        var state = new AGUIAgentThreadState
        {
            ThreadId = this.ThreadId,
            WrappedState = wrappedState,
        };

        return JsonSerializer.SerializeToElement(state, AGUIJsonSerializerContext.Default.AGUIAgentThreadState);
    }

    internal sealed class AGUIAgentThreadState
    {
        public string ThreadId { get; set; } = string.Empty;
        public JsonElement WrappedState { get; set; }
    }
}
