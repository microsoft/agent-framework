// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.AGUI;

internal sealed class AGUIAgentThread : InMemoryAgentThread
{
    public AGUIAgentThread()
        : base()
    {
        this.ThreadId = Guid.NewGuid().ToString();
    }

    public AGUIAgentThread(JsonElement serializedThreadState, JsonSerializerOptions? jsonSerializerOptions = null)
        : base(UnwrapState(serializedThreadState), jsonSerializerOptions)
    {
        this.ThreadSerializationOptions = jsonSerializerOptions;
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

    public string ThreadId { get; set; }

    public JsonSerializerOptions? ThreadSerializationOptions { get; set; }

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
