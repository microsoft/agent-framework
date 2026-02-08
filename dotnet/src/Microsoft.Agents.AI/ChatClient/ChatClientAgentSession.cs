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
public sealed class ChatClientAgentSession : AgentSession
{
    private ChatHistoryProvider? _chatHistoryProvider;

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatClientAgentSession"/> class.
    /// </summary>
    internal ChatClientAgentSession()
    {
    }

    /// <summary>
    /// Gets or sets the ID of the underlying service thread to support cases where the chat history is stored by the agent service.
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
    /// <item><description>The thread stores messages via the <see cref="AI.ChatHistoryProvider"/> and not in the agent service.</description></item>
    /// <item><description>This thread object is new and a server managed thread has not yet been created in the agent service.</description></item>
    /// </list>
    /// </para>
    /// <para>
    /// The id may also change over time where the id is pointing at a
    /// agent service managed thread, and the default behavior of a service is
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
                // If we have a ChatHistoryProvider already, we shouldn't switch the session to use a conversation id
                // since it means that the session contents will essentially be deleted, and the session will not work
                // with the original agent anymore.
                throw new InvalidOperationException("Only the ConversationId or ChatHistoryProvider may be set, but not both and switching from one to another is not supported.");
            }

            field = Throw.IfNullOrWhitespace(value);
        }
    }

    /// <summary>
    /// Gets or sets the <see cref="AI.ChatHistoryProvider"/> used by this thread, for cases where messages should be stored in a custom location.
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
    /// <item><description>The thread stores messages in the agent service and just has an id to the remove thread, instead of in an <see cref="AI.ChatHistoryProvider"/>.</description></item>
    /// <item><description>This thread object is new it is not yet clear whether it will be backed by a server managed thread or an <see cref="AI.ChatHistoryProvider"/>.</description></item>
    /// </list>
    /// </para>
    /// </remarks>
    public ChatHistoryProvider? ChatHistoryProvider
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
                // If we have a conversation id already, we shouldn't switch the session to use a ChatHistoryProvider
                // since it means that the session will not work with the original agent anymore.
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
    /// Creates a new instance of the <see cref="ChatClientAgentSession"/> class from previously serialized state.
    /// </summary>
    /// <param name="serializedState">A <see cref="JsonElement"/> representing the serialized state of the session.</param>
    /// <param name="jsonSerializerOptions">Optional settings for customizing the JSON deserialization process.</param>
    /// <param name="chatHistoryProviderFactory">
    /// An optional factory function to create a custom <see cref="AI.ChatHistoryProvider"/> from its serialized state.
    /// If not provided, the default <see cref="InMemoryChatHistoryProvider"/> will be used.
    /// </param>
    /// <param name="aiContextProviderFactory">
    /// An optional factory function to create a custom <see cref="AIContextProvider"/> from its serialized state.
    /// If not provided, no context provider will be configured.
    /// </param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A task representing the asynchronous operation. The task result contains the deserialized <see cref="ChatClientAgentSession"/>.</returns>
    internal static async Task<ChatClientAgentSession> DeserializeAsync(
        JsonElement serializedState,
        JsonSerializerOptions? jsonSerializerOptions = null,
        Func<JsonElement, JsonSerializerOptions?, CancellationToken, ValueTask<ChatHistoryProvider>>? chatHistoryProviderFactory = null,
        Func<JsonElement, JsonSerializerOptions?, CancellationToken, ValueTask<AIContextProvider>>? aiContextProviderFactory = null,
        CancellationToken cancellationToken = default)
    {
        if (serializedState.ValueKind != JsonValueKind.Object)
        {
            throw new ArgumentException("The serialized session state must be a JSON object.", nameof(serializedState));
        }

        var state = serializedState.Deserialize(
            AgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(SessionState))) as SessionState;

        var session = new ChatClientAgentSession();

        session.AIContextProvider = aiContextProviderFactory is not null
            ? await aiContextProviderFactory.Invoke(state?.AIContextProviderState ?? default, jsonSerializerOptions, cancellationToken).ConfigureAwait(false)
            : null;

        if (state?.ConversationId is string sessionId)
        {
            session.ConversationId = sessionId;

            // Since we have an ID, we should not have a ChatHistoryProvider and we can return here.
            return session;
        }

        session._chatHistoryProvider =
            chatHistoryProviderFactory is not null
                ? await chatHistoryProviderFactory.Invoke(state?.ChatHistoryProviderState ?? default, jsonSerializerOptions, cancellationToken).ConfigureAwait(false)
                : new InMemoryChatHistoryProvider(state?.ChatHistoryProviderState ?? default, jsonSerializerOptions); // default to an in-memory ChatHistoryProvider

        return session;
    }

    /// <inheritdoc/>
    internal JsonElement Serialize(JsonSerializerOptions? jsonSerializerOptions = null)
    {
        JsonElement? chatHistoryProviderState = this._chatHistoryProvider?.Serialize(jsonSerializerOptions);

        JsonElement? aiContextProviderState = this.AIContextProvider?.Serialize(jsonSerializerOptions);

        var state = new SessionState
        {
            ConversationId = this.ConversationId,
            ChatHistoryProviderState = chatHistoryProviderState is { ValueKind: not JsonValueKind.Undefined } ? chatHistoryProviderState : null,
            AIContextProviderState = aiContextProviderState is { ValueKind: not JsonValueKind.Undefined } ? aiContextProviderState : null,
        };

        return JsonSerializer.SerializeToElement(state, AgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(SessionState)));
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null) =>
        base.GetService(serviceType, serviceKey)
            ?? this.AIContextProvider?.GetService(serviceType, serviceKey)
            ?? this.ChatHistoryProvider?.GetService(serviceType, serviceKey);

    [DebuggerBrowsable(DebuggerBrowsableState.Never)]
    private string DebuggerDisplay =>
        this.ConversationId is { } conversationId ? $"ConversationId = {conversationId}" :
        this._chatHistoryProvider is InMemoryChatHistoryProvider inMemoryChatHistoryProvider ? $"Count = {inMemoryChatHistoryProvider.Count}" :
        this._chatHistoryProvider is { } chatHistoryProvider ? $"ChatHistoryProvider = {chatHistoryProvider.GetType().Name}" :
        "Count = 0";

    internal sealed class SessionState
    {
        public string? ConversationId { get; set; }

        public JsonElement? ChatHistoryProviderState { get; set; }

        public JsonElement? AIContextProviderState { get; set; }
    }
}
