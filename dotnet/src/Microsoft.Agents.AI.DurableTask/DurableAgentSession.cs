// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// An <see cref="AgentSession"/> implementation for durable agents.
/// </summary>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public sealed class DurableAgentSession : AgentSession
{
    internal DurableAgentSession(AgentSessionId sessionId)
    {
        this.SessionId = sessionId;
    }

    [JsonConstructor]
    internal DurableAgentSession(AgentSessionId sessionId, AgentSessionStateBag stateBag) : base(stateBag)
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
    internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var jso = jsonSerializerOptions ?? DurableAgentJsonUtilities.DefaultOptions;
        return JsonSerializer.SerializeToElement(this, jso.GetTypeInfo(typeof(DurableAgentSession)));
    }

    /// <summary>
    /// Deserializes a DurableAgentSession from JSON.
    /// </summary>
    /// <param name="serializedSession">The serialized thread data.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serializer options.</param>
    /// <returns>The deserialized DurableAgentSession.</returns>
    internal static DurableAgentSession Deserialize(JsonElement serializedSession, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (!serializedSession.TryGetProperty("sessionId", out JsonElement sessionIdElement) ||
            sessionIdElement.ValueKind != JsonValueKind.String)
        {
            throw new JsonException("Invalid or missing sessionId property.");
        }

        string sessionIdString = sessionIdElement.GetString() ?? throw new JsonException("sessionId property is null.");
        AgentSessionId sessionId = AgentSessionId.Parse(sessionIdString);
        AgentSessionStateBag stateBag = serializedSession.TryGetProperty("stateBag", out JsonElement stateBagElement)
            ? AgentSessionStateBag.Deserialize(stateBagElement)
            : new AgentSessionStateBag();

        return new DurableAgentSession(sessionId, stateBag);
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
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

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay =>
        $"SessionId = {this.SessionId}, StateBag Count = {this.StateBag.Count}";
}
