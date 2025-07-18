// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Agent thread that supports storing messages in memory, in a 3rd party service, or in the agent service.
/// </summary>
public sealed class MessageStoringAgentThread : AgentThread
{
    private readonly List<ChatMessage> _chatMessages = [];
    private readonly IChatMessagesStorable? _chatMessagesStorable;
    private MessageStoringThreadStorageLocation _type = MessageStoringThreadStorageLocation.Unknown;

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageStoringAgentThread"/> class.
    /// </summary>
    public MessageStoringAgentThread()
    {
        this.StorageLocation = MessageStoringThreadStorageLocation.Unknown;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageStoringAgentThread"/> class.
    /// </summary>
    /// <param name="id">The id of an existing server side thread to continue.</param>
    /// <remarks>
    /// This constructor creates a <see cref="MessageStoringAgentThread"/> that supports in-service message storage.
    /// </remarks>
    public MessageStoringAgentThread(string id)
    {
        Throw.IfNullOrWhitespace(id);

        this.Id = id;
        this.StorageLocation = MessageStoringThreadStorageLocation.ConversationId;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageStoringAgentThread"/> class.
    /// </summary>
    /// <param name="messages">A set of initial messages to seed the thread with.</param>
    /// <remarks>
    /// This constructor creates a <see cref="MessageStoringAgentThread"/> that supports local in-memory message storage.
    /// </remarks>
    public MessageStoringAgentThread(IEnumerable<ChatMessage> messages)
    {
        Throw.IfNull(messages);

        this._chatMessages.AddRange(messages);
        this.StorageLocation = MessageStoringThreadStorageLocation.AgentThreadManaged;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageStoringAgentThread"/> class.
    /// </summary>
    /// <param name="chatMessagesStorable">An implementation of <see cref="IChatMessagesStorable"/> to use for storing messages.</param>
    /// <param name="threadStateJson">A string representing the thread state, if any.</param>
    /// <param name="jsonSerializerOptions">Optional <see cref="JsonSerializerOptions"/> to use for deserializing the thread state.</param>
    public MessageStoringAgentThread(IChatMessagesStorable? chatMessagesStorable, string? threadStateJson, JsonSerializerOptions? jsonSerializerOptions)
    {
        this._chatMessagesStorable = chatMessagesStorable;
        this.StorageLocation = MessageStoringThreadStorageLocation.Unknown;

        if (threadStateJson is not null)
        {
            jsonSerializerOptions ??= new JsonSerializerOptions();
            jsonSerializerOptions.TypeInfoResolver = JsonTypeInfoResolver.Combine(jsonSerializerOptions?.TypeInfoResolver, ThreadStateJsonSerializerContext.Default);

#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
            var parsedThreadState = JsonSerializer.Deserialize(
                threadStateJson,
                typeof(ThreadState),
                jsonSerializerOptions) as ThreadState;
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code

            if (parsedThreadState is null)
            {
                throw new InvalidOperationException("The provided thread state is not valid.");
            }

            this.Id = parsedThreadState.Id;
            this.StorageLocation = parsedThreadState.StorageLocation;
            this._chatMessages.AddRange(parsedThreadState.Messages);
        }
    }

    /// <summary>
    /// Gets or sets the storage location of the thread.
    /// </summary>
    public MessageStoringThreadStorageLocation StorageLocation
    {
        get { return this._type; }
        set
        {
            if (this._type != MessageStoringThreadStorageLocation.Unknown && this._type != value)
            {
                Throw.InvalidOperationException($"The thread {nameof(this.StorageLocation)} cannot be changed from {this._type} to {value} after it has been set.");
            }

            this._type = value;
        }
    }

#pragma warning disable CS1998 // Async method lacks 'await' operators and will run synchronously

    /// <inheritdoc/>
    public async IAsyncEnumerable<ChatMessage> GetMessagesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (this._chatMessagesStorable is not null)
        {
            if (this.Id is null)
            {
                // If the thread has no id, there are no message to retrieve.
                yield break;
            }

            // If a store has been provided, we need to retrieve the messages from the store.
            var messages = await this._chatMessagesStorable.GetMessagesAsync(this.Id, cancellationToken).ConfigureAwait(false);
            foreach (var message in messages)
            {
                yield return message;
            }
            yield break;
        }

        // If we have no store, we return the messages from the in-memory list.
        foreach (var message in this._chatMessages)
        {
            yield return message;
        }
    }

    /// <inheritdoc/>
    public override string Serialize(JsonSerializerOptions? jsonSerializerOptions = default)
    {
        jsonSerializerOptions ??= new JsonSerializerOptions();
        jsonSerializerOptions.TypeInfoResolver = JsonTypeInfoResolver.Combine(jsonSerializerOptions?.TypeInfoResolver, ThreadStateJsonSerializerContext.Default);

        ThreadState state = new()
        {
            Id = this.Id,
            StorageLocation = this.StorageLocation,
            Messages = this._chatMessages
        };

#pragma warning disable IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
        return JsonSerializer.Serialize(state, typeof(ThreadState), jsonSerializerOptions);
#pragma warning restore IL3050 // Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
#pragma warning restore IL2026 // Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
    }

#pragma warning restore CS1998 // Async method lacks 'await' operators and will run synchronously

    /// <inheritdoc/>
    protected override async Task OnNewMessagesAsync(IReadOnlyCollection<ChatMessage> newMessages, CancellationToken cancellationToken = default)
    {
        switch (this.StorageLocation)
        {
            case MessageStoringThreadStorageLocation.AgentThreadManaged:
                // If a store has been provided, we need to add the messages to the store.
                if (this._chatMessagesStorable is not null)
                {
                    await this._chatMessagesStorable.AddMessagesAsync(this.Id, newMessages, cancellationToken).ConfigureAwait(false);
                    break;
                }

                // If we have no store, we add the messages to the in-memory list.
                this._chatMessages.AddRange(newMessages);
                break;

            case MessageStoringThreadStorageLocation.ConversationId:
                // If the thread messages are stored in the service
                // there is nothing to do here, since invoking the
                // service should already update the thread.
                break;

            default:
                throw new UnreachableException();
        }
    }

    internal class ThreadState
    {
        public string? Id { get; set; }
        public MessageStoringThreadStorageLocation StorageLocation { get; set; } = MessageStoringThreadStorageLocation.Unknown;
        public List<ChatMessage> Messages { get; set; } = [];
    }
}

[JsonSourceGenerationOptions(
    PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    UseStringEnumConverter = true)]
[JsonSerializable(typeof(MessageStoringAgentThread.ThreadState))]
internal sealed partial class ThreadStateJsonSerializerContext : JsonSerializerContext;
