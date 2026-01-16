// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides a thread implementation for use with <see cref="ChatClientAgent"/>.
/// </summary>
[DebuggerDisplay("{DebuggerDisplay,nq}")]
public sealed class ChatClientAgentThread : AgentThread
{
    private AIContextProvider? _chatHistoryProvider;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentThread"/> class.
    /// </summary>
    internal ChatClientAgentThread()
    {
    }

    /// <summary>
    /// Gets or sets the ID of the underlying service thread to support cases where the chat history is stored by the underlying AI service that the agent uses.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Note that either <see cref="ConversationId"/> or <see cref="ChatHistoryProvider "/> may be set, but not both.
    /// If <see cref="ChatHistoryProvider "/> is not null, setting <see cref="ConversationId"/> will throw an
    /// <see cref="InvalidOperationException "/> exception.
    /// </para>
    /// <para>
    /// This property may be null in the following cases:
    /// <list type="bullet">
    /// <item><description>The thread stores messages via the <see cref="ChatHistoryProvider"/> and not in the underlying AI service.</description></item>
    /// <item><description>This <see cref="AgentThread"/> object is new and server managed chat history has not yet been created in the underlying AI service.</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// The id may also change over time if the id is pointing at AI service managed chat history, and the default behavior of a service is
    /// to fork the thread with each iteration.
    /// </para>
    /// </remarks>
    /// <exception cref="InvalidOperationException">Attempted to set a conversation ID but a <see cref="ChatHistoryProvider"/> is already set.</exception>
    public string? ConversationId
    {
        get;
        internal set
        {
            if (string.IsNullOrWhiteSpace(field) && string.IsNullOrWhiteSpace(value))
            {
                return;
            }

            if (this._chatHistoryProvider is not null)
            {
                // If we have a chat history provider already, we shouldn't switch the thread to use a conversation id
                // since it means that the thread contents will essentially be deleted, and the thread will not work
                // with the original agent anymore.
                throw new InvalidOperationException("Only the ConversationId or ChatHistoryProvider may be set, but not both and switching from one to another is not supported.");
            }

            field = Throw.IfNullOrWhitespace(value);
        }
    }

    /// <summary>
    /// Gets or sets the chat history provider used by this thread, for cases where messages are not stored in the underlying AI service that the agent uses.
    /// </summary>
    /// <remarks>
    /// <para>
    /// Note that either <see cref="ConversationId"/> or <see cref="ChatHistoryProvider "/> may be set, but not both.
    /// If <see cref="ConversationId"/> is not null, and <see cref="ChatHistoryProvider "/> is set, <see cref="ConversationId"/>
    /// will be reverted to null, and vice versa.
    /// </para>
    /// <para>
    /// This property may be null in the following cases:
    /// <list type="bullet">
    /// <item><description>Chat history is stored in the underlying AI service and just has an id to the remote chat history.</description></item>
    /// <item><description>This <see cref="AgentThread"/> object is new it is not yet clear whether it will be backed by AI service managed chat history or a <see cref="ChatHistoryProvider"/>.</description></item>
    /// </list>
    /// </para>
    /// </remarks>
    public AIContextProvider? ChatHistoryProvider
    {
        get => this._chatHistoryProvider;
        internal set
        {
            if (this._chatHistoryProvider is null && value is null)
            {
                return;
            }

            if (!string.IsNullOrWhiteSpace(this.ConversationId))
            {
                // If we have a conversation id already, we shouldn't switch the thread to use a chat history provider
                // since it means that the thread will not work with the original agent anymore.
                throw new InvalidOperationException("Only the ConversationId or ChatHistoryProvider may be set, but not both and switching from one to another is not supported.");
            }

            this._chatHistoryProvider = Throw.IfNull(value);
        }
    }

    /// <summary>
    /// Gets or sets the <see cref="AIContextProvider"/> used by this thread to provide additional context to the AI model before each invocation.
    /// </summary>
    public AIContextProvider? AIContextProvider { get; internal set; }

    /// <summary>
    /// Creates a new instance of the <see cref="ChatClientAgentThread"/> class from previously serialized state.
    /// </summary>
    /// <param name="serializedThreadState">A <see cref="JsonElement"/> representing the serialized state of the thread.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="chatHistoryProviderFactory">
    /// An optional factory function to create a custom chat history provider from its serialized state.
    /// If not provided, the default in-memory chat history provider will be used.
    /// </param>
    /// <param name="aiContextProviderFactory">
    /// An optional factory function to create a custom <see cref="AIContextProvider"/> from its serialized state.
    /// If not provided, no context provider will be configured.
    /// </param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task representing the asynchronous operation. The task result contains the deserialized <see cref="ChatClientAgentThread"/>.</returns>
    internal static async Task<ChatClientAgentThread> DeserializeAsync(
        JsonElement serializedThreadState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        Func<JsonElement, JsonSerializerOptions?, CancellationToken, ValueTask<AIContextProvider>>? chatHistoryProviderFactory = null,
        Func<JsonElement, JsonSerializerOptions?, CancellationToken, ValueTask<AIContextProvider>>? aiContextProviderFactory = null,
        CancellationToken cancellationToken = default)
    {
        if (serializedThreadState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized thread state must be a JSON object.", nameof(serializedThreadState));
        }

        var state = serializedThreadState.Deserialize(
            AgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ThreadState))) as ThreadState;

        var thread = new ChatClientAgentThread();

        thread.AIContextProvider = aiContextProviderFactory is not null
            ? await aiContextProviderFactory.Invoke(state?.AIContextProviderState ?? default, jsonSerializerOptions, cancellationToken).ConfigureAwait(false)
            : null;

        if (state?.ConversationId is string threadId)
        {
            thread.ConversationId = threadId;

            // Since we have an ID, we should not have a chat history provider and we can return here.
            return thread;
        }

        thread._chatHistoryProvider =
            chatHistoryProviderFactory is not null
                ? await chatHistoryProviderFactory.Invoke(state?.ChatHistoryProviderState ?? default, jsonSerializerOptions, cancellationToken).ConfigureAwait(false)
                : new InMemoryChatHistoryProvider(state?.ChatHistoryProviderState ?? default, jsonSerializerOptions); // default to an in-memory store

        return thread;
    }

    /// <inheritdoc/>
    public override JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        JsonElement? chatHistoryProviderState = this._chatHistoryProvider?.Serialize(jsonSerializerOptions);

        JsonElement? aiContextProviderState = this.AIContextProvider?.Serialize(jsonSerializerOptions);

        var state = new ThreadState
        {
            ConversationId = this.ConversationId,
            ChatHistoryProviderState = chatHistoryProviderState is { ValueKind: not JsonValueKind.Undefined } ? chatHistoryProviderState : null,
            AIContextProviderState = aiContextProviderState is { ValueKind: not JsonValueKind.Undefined } ? aiContextProviderState : null,
        };

        return JsonSerializer.SerializeToElement(state, AgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(ThreadState)));
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        base.GetService(serviceType, serviceKey)
            ?? this.AIContextProvider?.GetService(serviceType, serviceKey)
            ?? this.ChatHistoryProvider?.GetService(serviceType, serviceKey);

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay =>
        this.ConversationId is { } conversationId ? $"ConversationId = {conversationId}" :
        this._chatHistoryProvider is InMemoryChatHistoryProvider inMemoryStore ? $"Count = {inMemoryStore.Count}" :
        this._chatHistoryProvider is { } store ? $"Store = {store.GetType().Name}" :
        "Count = 0";

    internal sealed class ThreadState
    {
        public string? ConversationId { get; set; }

        public JsonElement? ChatHistoryProviderState { get; set; }

        public JsonElement? AIContextProviderState { get; set; }
    }
}
