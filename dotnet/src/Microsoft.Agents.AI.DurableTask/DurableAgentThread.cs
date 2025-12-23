// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// An agent thread implementation for durable agents.
/// </summary>
[DebuggerDisplay("{SessionId}")]
public sealed class DurableAgentThread : AgentThread
{
    [JsonConstructor]
    internal DurableAgentThread(AgentSessionId sessionId)
    {
        this.SessionId = sessionId;
    }

    /// <summary>
    /// Gets the agent session ID.
    /// </summary>
    [JsonInclude]
    [JsonPropertyName("sessionId")]
    internal AgentSessionId SessionId { get; }

    /// <inheritdoc/>
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        return JsonSerializer.SerializeToElement(
            this,
            DurableAgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(DurableAgentThread)));
    }

    /// <summary>
    /// Deserializes a DurableAgentThread from JSON.
    /// </summary>
    /// <param name="serializedThread">The serialized thread data.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serializer options.</param>
    /// <returns>The deserialized DurableAgentThread.</returns>
    internal static DurableAgentThread Deserialize(JsonElement serializedThread, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (!serializedThread.TryGetProperty("sessionId", out JsonElement sessionIdElement) ||
            sessionIdElement.ValueKind != JsonValueKind.String)
        {
            throw new JsonException("Invalid or missing sessionId property.");
        }

        string sessionIdString = sessionIdElement.GetString() ?? throw new JsonException("sessionId property is null.");
        AgentSessionId sessionId = AgentSessionId.Parse(sessionIdString);
        return new DurableAgentThread(sessionId);
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        // This is a common convention for MAF agents.
        if (serviceType == typeof(AgentThreadMetadata))
        {
            return new AgentThreadMetadata(conversationId: this.SessionId.ToString());
        }

        if (serviceType == typeof(AgentSessionId))
        {
            return this.SessionId;
        }

        return base.GetService(serviceType, serviceKey);
    }

    /// <inheritdoc/>
    public override string ToString()
    {
        return this.SessionId.ToString();
    }
}
