// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Chat client agent thread.
/// </summary>
[JsonConverter(typeof(Converter))]
public sealed class ChatClientAgentThread : AgentThread, IMessagesRetrievableThread
{
    private readonly List<ChatMessage> _chatMessages = [];

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentThread"/> class.
    /// </summary>
    public ChatClientAgentThread()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentThread"/> class.
    /// </summary>
    /// <param name="id">The id of an existing server side thread to continue.</param>
    /// <remarks>
    /// This constructor creates a <see cref="ChatClientAgentThread"/> that supports in-service message storage.
    /// </remarks>
    public ChatClientAgentThread(string id)
    {
        Throw.IfNullOrWhitespace(id);

        this.Id = id;
        this.StorageLocation = ChatClientAgentThreadType.ConversationId;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentThread"/> class.
    /// </summary>
    /// <param name="messages">A set of initial messages to seed the thread with.</param>
    /// <remarks>
    /// This constructor creates a <see cref="ChatClientAgentThread"/> that supports local in-memory message storage.
    /// </remarks>
    public ChatClientAgentThread(IEnumerable<ChatMessage> messages)
    {
        Throw.IfNull(messages);

        this._chatMessages.AddRange(messages);
        this.StorageLocation = ChatClientAgentThreadType.InMemoryMessages;
    }

    /// <summary>
    /// Gets the location of the thread contents.
    /// </summary>
    internal ChatClientAgentThreadType? StorageLocation { get; set; }

#pragma warning disable CS1998 // Async method lacks 'await' operators and will run synchronously
    /// <inheritdoc/>
    public async IAsyncEnumerable<ChatMessage> GetMessagesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        foreach (var message in this._chatMessages)
        {
            yield return message;
        }
    }

#pragma warning restore CS1998 // Async method lacks 'await' operators and will run synchronously

    /// <inheritdoc/>
    protected override Task OnNewMessagesAsync(IReadOnlyCollection<ChatMessage> newMessages, CancellationToken cancellationToken = default)
    {
        switch (this.StorageLocation)
        {
            case ChatClientAgentThreadType.InMemoryMessages:
                this._chatMessages.AddRange(newMessages);
                break;
            case ChatClientAgentThreadType.ConversationId:
                // If the thread messages are stored in the service
                // there is nothing to do here, since invoking the
                // service should already update the thread.
                break;
            default:
                throw new UnreachableException();
        }

        return Task.CompletedTask;
    }

    /// <summary>
    /// Provides a <see cref="JsonConverter"/> for <see cref="ChatClientAgentThread"/> objects.
    /// </summary>
    [EditorBrowsable(EditorBrowsableState.Never)]
    public sealed class Converter : JsonConverter<ChatClientAgentThread>
    {
        /// <inheritdoc/>
        public override ChatClientAgentThread? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
        {
            if (reader.TokenType != JsonTokenType.StartObject)
            {
                throw new JsonException("Expected StartObject token");
            }

            using var doc = JsonDocument.ParseValue(ref reader);
            var root = doc.RootElement;

            // Extract properties from JSON
            string? id = null;
            if (root.TryGetProperty("id", out var idProperty))
            {
                id = idProperty.GetString();
            }

            List<ChatMessage>? messages = null;
            if (root.TryGetProperty("messages", out var messagesProperty))
            {
                if (messagesProperty.ValueKind == JsonValueKind.Array)
                {
                    messages = [];
                    foreach (var messageElement in messagesProperty.EnumerateArray())
                    {
                        var message = messageElement.Deserialize(options.GetTypeInfo<ChatMessage>(AgentsJsonContext.Default));
                        if (message != null)
                        {
                            messages.Add(message);
                        }
                    }
                }
            }

            // Create the appropriate instance based on available data
            // StorageLocation will be set automatically by the constructors
            ChatClientAgentThread thread;
            if (messages?.Count > 0)
            {
                thread = new ChatClientAgentThread(messages);
            }
            else if (!string.IsNullOrWhiteSpace(id))
            {
                thread = new ChatClientAgentThread(id);
            }
            else
            {
                thread = new ChatClientAgentThread();
            }

            // Override Id if it was explicitly set in JSON (for cases where messages exist but ID is also provided)
            if (id != null)
            {
                thread.Id = id;
            }

            return thread;
        }

        /// <inheritdoc/>
        public override void Write(Utf8JsonWriter writer, ChatClientAgentThread value, JsonSerializerOptions options)
        {
            writer.WriteStartObject();

            // Write base properties
            if (value.Id != null)
            {
                writer.WriteString("id", value.Id);
            }

            // Write messages if in memory storage (StorageLocation is determined by presence of messages vs ID)
            if (value.StorageLocation == ChatClientAgentThreadType.InMemoryMessages)
            {
                writer.WritePropertyName("messages");
                JsonSerializer.Serialize(writer, value._chatMessages, options.GetTypeInfo<List<ChatMessage>>(AgentsJsonContext.Default));
            }

            writer.WriteEndObject();
        }
    }
}
