// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a thread implementation for use with <see cref="ChatClientAgent"/>.
/// </summary>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public sealed class ChatClientAgentSession : AgentSession
{
    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentSession"/> class.
    /// </summary>
    internal ChatClientAgentSession()
    {
    }

    [JsonConstructor]
    internal ChatClientAgentSession(string? conversationId, AgentSessionStateBag? stateBag) : base(stateBag ?? new())
    {
        this.ConversationId = conversationId;
    }

    /// <summary>
    /// Gets or sets the ID of the underlying service chat history to support cases where the chat history is stored by the agent service.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This property may be null in the following cases:
    /// <list type="bullet">
    /// <item><description>The agent stores messages via a <see cref="ChatHistoryProvider"/> and not in the agent service.</description></item>
    /// <item><description>This session object is new and server managed chat history has not yet been created in the agent service.</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// The id may also change over time where the id is pointing at
    /// agent service managed chat history, and the default behavior of a service is
    /// to fork the chat history with each iteration.
    /// </para>
    /// </remarks>
    [JsonPropertyName("conversationId")]
    public string? ConversationId
    {
        get;
        internal set
        {
            if (string.IsNullOrWhiteSpace(field) && string.IsNullOrWhiteSpace(value))
            {
                return;
            }

            field = Throw.IfNullOrWhitespace(value);
        }
    }

    /// <summary>
    /// Creates a new instance of the <see cref="ChatClientAgentSession"/> class from previously serialized state.
    /// </summary>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the serialized state of the session.</param>
    /// <param name="jsonSerializerOptions">Optional JSON serialization options to use instead of the default options.</param>
    /// <returns>The deserialized <see cref="ChatClientAgentSession"/>.</returns>
    internal static ChatClientAgentSession Deserialize(JsonElement serializedState, JsonSerializerOptions? jsonSerializerOptions = null)
    {
        if (serializedState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized session state must be a JSON object.", nameof(serializedState));
        }

        var jso = jsonSerializerOptions ?? AgentJsonUtilities.DefaultOptions;
        return serializedState.Deserialize(jso.GetTypeInfo(typeof(ChatClientAgentSession))) as ChatClientAgentSession
            ?? new ChatClientAgentSession();
    }

    /// <inheritdoc/>
    internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        var jso = jsonSerializerOptions ?? AgentJsonUtilities.DefaultOptions;
        return JsonSerializer.SerializeToElement(this, jso.GetTypeInfo(typeof(ChatClientAgentSession)));
    }

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay =>
        this.ConversationId is { } conversationId ? $"ConversationId = {conversationId}, StateBag Count = {this.StateBag.Count}" :
        $"StateBag Count = {this.StateBag.Count}";
}
