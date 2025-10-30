// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;

internal sealed class AgentStateStore
{
    private readonly Dictionary<string, JsonElement?> _agentStateStore = new();

    public void PersistAgentState(AgentThread thread, object? continuationToken)
    {
        this._agentStateStore["thread"] = thread.Serialize();
        this._agentStateStore["continuationToken"] = JsonSerializer.SerializeToElement(continuationToken, AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ResponseContinuationToken)));
    }

    public void RestoreAgentState(AIAgent agent, out AgentThread thread, out object? continuationToken)
    {
        JsonElement serializedThread = this._agentStateStore["thread"] ?? throw new InvalidOperationException("No serialized thread found in state store.");
        JsonElement? serializedToken = this._agentStateStore["continuationToken"];

        thread = agent.DeserializeThread(serializedThread);
        continuationToken = serializedToken?.Deserialize(AgentAbstractionsJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ResponseContinuationToken)));
    }
}
