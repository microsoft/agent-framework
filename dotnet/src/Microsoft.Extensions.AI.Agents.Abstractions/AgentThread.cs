// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Base abstraction for all agent threads.
/// A thread represents a specific conversation with an agent.
/// </summary>
public class AgentThread
{
    private string? _id;
    private IChatMessageStore? _chatMessageStore;

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentThread"/> class.
    /// </summary>
    public AgentThread()
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentThread"/> class.
    /// </summary>
    /// <param name="id">The id of an existing server-side thread to continue.</param>
    /// <remarks>
    /// This constructor creates an <see cref="AgentThread"/> that supports storing chat history in the agent service.
    /// </remarks>
    public AgentThread(string id)
    {
        this._id = Throw.IfNullOrWhitespace(id);
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AgentThread"/> class.
    /// </summary>
    /// <param name="chatMessageStore">The <see cref="IChatMessageStore"/> used to store chat messages.</param>
    /// <remarks>
    /// This constructor creates an <see cref="AgentThread"/> with an optional <see cref="IChatMessageStore"/> that can store messages if the agent service does not have built in support for this.
    /// </remarks>
    public AgentThread(IChatMessageStore? chatMessageStore)
    {
        this._chatMessageStore = chatMessageStore;
    }

    /// <summary>
    /// Gets or sets the id of the current thread to support cases where the thread is owned by the agent service.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Note that either <see cref="Id"/> or <see cref="ChatMessageStore"/> may be set, but not both.
    /// If <see cref="ChatMessageStore"/> is not null, and <see cref="Id"/> is set, <see cref="ChatMessageStore"/>
    /// will be reverted to null, and vice versa.
    /// </para>
    /// <para>
    /// This property may be null in the following cases:
    /// <list type="bullet">
    /// <item>The thread stores messages via the <see cref="IChatMessageStore"/> and not in the agent service.</item>
    /// <item>This thread object is new and a server managed thread has not yet been created in the agent service.</item>
    /// </list>
    /// </para>
    /// <para>
    /// The id may also change over time where the the id is pointing at a
    /// agent service managed thread, and the default behavior of a service is
    /// to fork the thread with each iteration.
    /// </para>
    /// </remarks>
    public string? Id
    {
        get { return this._id; }
        set
        {
            this._id = Throw.IfNullOrWhitespace(value);
            this._chatMessageStore = null;
        }
    }

    /// <summary>
    /// Gets or sets the <see cref="IChatMessageStore"/> used by this thread, for cases where messages should be stored in a custom location.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Note that either <see cref="Id"/> or <see cref="ChatMessageStore"/> may be set, but not both.
    /// If <see cref="Id"/> is not null, and <see cref="ChatMessageStore"/> is set, <see cref="Id"/>
    /// will be reverted to null, and vice versa.
    /// </para>
    /// <para>
    /// This property may be null in the following cases:
    /// <list type="bullet">
    /// <item>The thread stores messages in the agent service and just has an id to the remove thread, instead of in an <see cref="IChatMessageStore"/>.</item>
    /// <item>This thread object is new it is not yet clear whether it will be backed by a server managed thread or an <see cref="IChatMessageStore"/>.</item>
    /// </list>
    /// </para>
    /// </remarks>
    public IChatMessageStore? ChatMessageStore
    {
        get { return this._chatMessageStore; }
        set
        {
            this._chatMessageStore = Throw.IfNull(value);
            this._id = null;
        }
    }

    /// <summary>
    /// Retrieves any messages stored in the <see cref="IChatMessageStore"/> of the thread, otherwise returns an empty collection.
    /// </summary>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>The messages from the <see cref="IChatMessageStore"/> in ascending chronological order, with the oldest message first.</returns>
    public virtual async IAsyncEnumerable<ChatMessage> GetMessagesAsync([EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        if (this._chatMessageStore is not null)
        {
            var messages = await this._chatMessageStore!.GetMessagesAsync(cancellationToken).ConfigureAwait(false);
            foreach (var message in messages)
            {
                yield return message;
            }
        }
    }

    /// <summary>
    /// This method is called when new messages have been contributed to the chat by any participant.
    /// </summary>
    /// <remarks>
    /// Inheritors can use this method to update their context based on the new message.
    /// </remarks>
    /// <param name="newMessages">The new messages.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A task that completes when the context has been updated.</returns>
    /// <exception cref="InvalidOperationException">The thread has been deleted.</exception>
    protected internal virtual async Task OnNewMessagesAsync(IReadOnlyCollection<ChatMessage> newMessages, CancellationToken cancellationToken = default)
    {
        switch (this)
        {
            case { ChatMessageStore: not null }:
                // If a store has been provided, we need to add the messages to the store.
                await this._chatMessageStore!.AddMessagesAsync(newMessages, cancellationToken).ConfigureAwait(false);
                break;

            case { Id: not null }:
                // If the thread messages are stored in the service
                // there is nothing to do here, since invoking the
                // service should already update the thread.
                break;

            default:
                throw new UnreachableException();
        }
    }

    /// <summary>
    /// Deserializes the state contained in the provided <see cref="JsonElement"/> into the properties on this thread.
    /// </summary>
    /// <param name="stateElement">A <see cref="JsonElement"/> representing the state of the thread.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    public virtual async Task DeserializeAsync(JsonElement stateElement, JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        jsonSerializerOptions ??= AgentAbstractionsJsonUtilities.DefaultOptions;

        // Deserialize the first element as the thread ID.
        var state = JsonSerializer.Deserialize(
            stateElement,
            jsonSerializerOptions.GetTypeInfo(typeof(ThreadState))) as ThreadState;

        if (state?.Id is string threadId)
        {
            this.Id = threadId;

            // Since we have an ID, we should not have a chat message store and we can return here.
            return;
        }

        // If we don't have any IChatMessageStore state return here.
        if (state?.StoreState is null || state?.StoreState?.ValueKind is JsonValueKind.Undefined or JsonValueKind.Null)
        {
            return;
        }

        if (this._chatMessageStore is null)
        {
            // If we don't have a chat message store yet, create an in-memory one.
            this._chatMessageStore = new InMemoryChatMessageStore();
        }

        await this._chatMessageStore.DeserializeAsync(state!.StoreState.Value, jsonSerializerOptions, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Serializes the current object's state to a <see cref="JsonElement"/> using the specified serialization options.
    /// </summary>
    /// <param name="jsonSerializerOptions">The JSON serialization options to use.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="JsonElement"/> representation of the object's state.</returns>
    public virtual async Task<JsonElement> SerializeAsync(JsonSerializerOptions? jsonSerializerOptions = null, CancellationToken cancellationToken = default)
    {
        jsonSerializerOptions ??= AgentAbstractionsJsonUtilities.DefaultOptions;

        var storeState = this._chatMessageStore is null ?
            (JsonElement?)null :
            await this._chatMessageStore.SerializeAsync(jsonSerializerOptions, cancellationToken).ConfigureAwait(false);

        var state = new ThreadState
        {
            Id = this.Id,
            StoreState = storeState
        };

        return JsonSerializer.SerializeToElement(state, jsonSerializerOptions.GetTypeInfo(typeof(ThreadState)));
    }

    internal class ThreadState
    {
        public string? Id { get; set; }

        public JsonElement? StoreState { get; set; }
    }
}
