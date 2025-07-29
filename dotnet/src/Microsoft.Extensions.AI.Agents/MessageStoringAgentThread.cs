// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Agent thread that supports storing messages in memory, in a 3rd party service, or in the agent service.
/// </summary>
public sealed class MessageStoringAgentThread : AgentThread
{
    private IChatMessageStore? _chatMessageStore;
    private MessageStoringThreadStorageLocation _storageLocation = MessageStoringThreadStorageLocation.Unknown;

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageStoringAgentThread"/> class.
    /// </summary>
    public MessageStoringAgentThread()
    {
        this._storageLocation = MessageStoringThreadStorageLocation.Unknown;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageStoringAgentThread"/> class.
    /// </summary>
    /// <param name="id">The id of an existing server-side thread to continue.</param>
    /// <remarks>
    /// This constructor creates a <see cref="MessageStoringAgentThread"/> that supports in-service message storage.
    /// </remarks>
    public MessageStoringAgentThread(string id)
    {
        this.Id = Throw.IfNullOrWhitespace(id);
        this._storageLocation = MessageStoringThreadStorageLocation.AgentService;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageStoringAgentThread"/> class.
    /// </summary>
    /// <param name="chatMessageStore">The <see cref="IChatMessageStore"/> used to store chat messages.</param>
    public MessageStoringAgentThread(IChatMessageStore? chatMessageStore)
    {
        this._chatMessageStore = chatMessageStore;
        this._storageLocation = chatMessageStore is null ? MessageStoringThreadStorageLocation.Unknown : MessageStoringThreadStorageLocation.ChatMessageStore;
    }

    /// <summary>
    /// Gets the chat message store used by this thread, if any.
    /// </summary>
    public IChatMessageStore? ChatMessageStore => this._chatMessageStore;

    /// <summary>
    /// Updates a thread with <see cref="MessageStoringThreadStorageLocation"/> of <see cref="MessageStoringThreadStorageLocation.Unknown"/>
    /// to use an external <see cref="IChatMessageStore"/> for storing messages.
    /// </summary>
    /// <param name="chatMessageStore">The <see cref="IChatMessageStore"/> to use for storing messages. Defaults to <see cref="InMemoryChatMessageStore"/> if not provided.</param>
    public void UseChatMessageStoreStorage(IChatMessageStore? chatMessageStore = null)
    {
        if (this._storageLocation != MessageStoringThreadStorageLocation.Unknown)
        {
            Throw.InvalidOperationException($"{nameof(UseChatMessageStoreStorage)} can only be called on threads with a storage location of {nameof(MessageStoringThreadStorageLocation.Unknown)}.");
        }

        this._storageLocation = MessageStoringThreadStorageLocation.ChatMessageStore;
        this._chatMessageStore = chatMessageStore ?? new InMemoryChatMessageStore();
    }

    /// <summary>
    /// Updates a thread with <see cref="MessageStoringThreadStorageLocation"/> of <see cref="MessageStoringThreadStorageLocation.Unknown"/>
    /// to indicate that the messages are stored in the agent service under the provided conversation id.
    /// </summary>
    /// <param name="id">The conversation id under which the messages are stored.</param>
    public void UseAgentServiceStorage(string id)
    {
        if (this._storageLocation != MessageStoringThreadStorageLocation.Unknown)
        {
            Throw.InvalidOperationException($"{nameof(UseAgentServiceStorage)} can only be called on threads with a storage location of {nameof(MessageStoringThreadStorageLocation.Unknown)}.");
        }

        this._storageLocation = MessageStoringThreadStorageLocation.AgentService;
        this.Id = Throw.IfNullOrWhitespace(id);
    }

    /// <summary>
    /// Gets the storage location of the thread.
    /// </summary>
    public MessageStoringThreadStorageLocation StorageLocation
    {
        get { return this._storageLocation; }
    }

#pragma warning disable CS1998 // Async method lacks 'await' operators and will run synchronously

    /// <inheritdoc/>
    public async IAsyncEnumerable<ChatMessage> GetMessagesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (this.StorageLocation == MessageStoringThreadStorageLocation.ChatMessageStore)
        {
            // If a store has been provided, we need to retrieve the messages from the store.
            var messages = await this._chatMessageStore!.GetMessagesAsync(cancellationToken).ConfigureAwait(false);
            foreach (var message in messages)
            {
                yield return message;
            }

            yield break;
        }
    }

    /// <inheritdoc/>
    protected override async Task OnNewMessagesAsync(IReadOnlyCollection<ChatMessage> newMessages, CancellationToken cancellationToken = default)
    {
        switch (this.StorageLocation)
        {
            case MessageStoringThreadStorageLocation.ChatMessageStore:
                // If a store has been provided, we need to add the messages to the store.
                await this._chatMessageStore!.AddMessagesAsync(newMessages, cancellationToken).ConfigureAwait(false);
                break;

            case MessageStoringThreadStorageLocation.AgentService:
                // If the thread messages are stored in the service
                // there is nothing to do here, since invoking the
                // service should already update the thread.
                break;

            default:
                throw new UnreachableException();
        }
    }

    /// <inheritdoc/>
    public override async Task DeserializeAsync(JsonElement stateElement, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(stateElement);

        jsonSerializerOptions ??= AgentsJsonUtilities.DefaultOptions;

        var threadState = JsonSerializer.Deserialize(
            stateElement,
            jsonSerializerOptions.GetTypeInfo(typeof(ThreadState))) as ThreadState;

        if (threadState?.BaseState.ValueKind is not JsonValueKind.Undefined)
        {
            await base.DeserializeAsync(threadState!.BaseState, jsonSerializerOptions, cancellationToken).ConfigureAwait(false);
        }

        this._storageLocation = threadState?.StorageLocation ?? MessageStoringThreadStorageLocation.Unknown;

        // Only ChatMessageStore related deserialization left, so shortcut here if not ChatMessageStore.
        if (this._storageLocation != MessageStoringThreadStorageLocation.ChatMessageStore)
        {
            return;
        }

        this._chatMessageStore ??= new InMemoryChatMessageStore();

        // If we don't have any ChatMessageStore messages exit here.
        if (threadState?.StoreState is null || threadState?.StoreState?.ValueKind is JsonValueKind.Undefined or JsonValueKind.Null)
        {
            return;
        }

        // Deserialize the ChatMessageStore messages from the thread state.
        await this._chatMessageStore.DeserializeAsync(threadState!.StoreState.Value, jsonSerializerOptions, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        var baseElement = await base.SerializeAsync(jsonSerializerOptions, cancellationToken).ConfigureAwait(false);

        jsonSerializerOptions ??= AgentsJsonUtilities.DefaultOptions;

        var storeState = this._chatMessageStore is null ?
            (JsonElement?)null :
            await this._chatMessageStore.SerializeAsync(jsonSerializerOptions, cancellationToken).ConfigureAwait(false);

        ThreadState state = new()
        {
            BaseState = baseElement,
            StoreState = storeState,
            StorageLocation = this.StorageLocation
        };

        return JsonSerializer.SerializeToElement(state, jsonSerializerOptions.GetTypeInfo(typeof(ThreadState)));
    }

    internal class ThreadState
    {
        public JsonElement BaseState { get; set; }

        public JsonElement? StoreState { get; set; }

        public MessageStoringThreadStorageLocation StorageLocation { get; set; } = MessageStoringThreadStorageLocation.Unknown;
    }
}
