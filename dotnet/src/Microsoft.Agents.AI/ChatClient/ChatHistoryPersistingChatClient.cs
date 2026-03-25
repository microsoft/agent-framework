// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// A delegating chat client that notifies <see cref="ChatHistoryProvider"/> and <see cref="AIContextProvider"/>
/// instances of request and response messages after each individual call to the inner chat client,
/// or marks messages for later persistence depending on the configured mode.
/// </summary>
/// <remarks>
/// <para>
/// This decorator is intended to operate between the <see cref="FunctionInvokingChatClient"/> and the leaf
/// <see cref="IChatClient"/> in a <see cref="ChatClientAgent"/> pipeline.
/// </para>
/// <para>
/// In persist mode (the default), it ensures that providers are notified and the session's
/// <see cref="ChatClientAgentSession.ConversationId"/> is updated after each service call, so that
/// intermediate messages (e.g., tool calls and results) are saved even if the process is interrupted
/// mid-loop.
/// </para>
/// <para>
/// In mark-only mode (<see cref="MarkOnly"/> is <see langword="true"/>), it marks messages with metadata
/// but does not notify providers or update the <see cref="ChatClientAgentSession.ConversationId"/>.
/// Both are deferred to the <see cref="ChatClientAgent"/> at the end of the run, providing atomic
/// run semantics.
/// </para>
/// <para>
/// This chat client must be used within the context of a running <see cref="ChatClientAgent"/>. It retrieves the
/// current agent and session from <see cref="AIAgent.CurrentRunContext"/>, which is set automatically when an agent's
/// <see cref="AIAgent.RunAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/> or
/// <see cref="AIAgent.RunStreamingAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>
/// method is called. The <see cref="ChatClientAgent"/> ensures the run context always contains a resolved session,
/// even when the caller passes null. An <see cref="InvalidOperationException"/> is thrown if no run context is
/// available or if the agent is not a <see cref="ChatClientAgent"/>.
/// </para>
/// </remarks>
internal sealed class ChatHistoryPersistingChatClient : DelegatingChatClient
{
    /// <summary>
    /// The key used in <see cref="ChatMessage.AdditionalProperties"/> and <see cref="AIContent.AdditionalProperties"/>
    /// to mark messages and their content as already persisted to chat history.
    /// </summary>
    internal const string PersistedMarkerKey = "_chatHistoryPersisted";

    /// <summary>
    /// Initializes a new instance of the <see cref="ChatHistoryPersistingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying chat client that will handle the core operations.</param>
    /// <param name="markOnly">
    /// When <see langword="true"/>, messages are marked with metadata but not persisted immediately,
    /// and the session's <see cref="ChatClientAgentSession.ConversationId"/> is not updated.
    /// The <see cref="ChatClientAgent"/> will persist only the marked messages and update the
    /// conversation ID at the end of the run.
    /// When <see langword="false"/> (the default), messages are persisted and the conversation ID
    /// is updated immediately after each service call.
    /// </param>
    public ChatHistoryPersistingChatClient(IChatClient innerClient, bool markOnly = false)
        : base(innerClient)
    {
        this.MarkOnly = markOnly;
    }

    /// <summary>
    /// Gets a value indicating whether this decorator is in mark-only mode.
    /// </summary>
    /// <remarks>
    /// When <see langword="true"/>, messages are marked with metadata but not persisted immediately,
    /// and the session's <see cref="ChatClientAgentSession.ConversationId"/> is not updated.
    /// Both are deferred to the <see cref="ChatClientAgent"/> at the end of the run.
    /// When <see langword="false"/>, messages are persisted and the conversation ID is updated
    /// after each service call.
    /// </remarks>
    public bool MarkOnly { get; }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var (agent, session) = GetRequiredAgentAndSession();

        ChatResponse response;
        try
        {
            response = await base.GetResponseAsync(messages, options, cancellationToken).ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            var newRequestMessagesOnFailure = GetNewRequestMessages(messages);
            await agent.NotifyProvidersOfFailureAsync(session, ex, newRequestMessagesOnFailure, options, cancellationToken).ConfigureAwait(false);
            throw;
        }

        var newRequestMessages = GetNewRequestMessages(messages);

        if (this.ShouldDeferPersistence(options))
        {
            // In mark-only mode or when resuming from a continuation token, just mark messages
            // for later persistence by ChatClientAgent. Conversation ID and provider notification
            // are deferred to end-of-run. For continuation tokens, the end-of-run handler needs
            // to send the combined data from both the previous and current runs.
            MarkAsPersisted(newRequestMessages);
            MarkAsPersisted(response.Messages);
        }
        else
        {
            // In persist mode, persist immediately and update conversation ID.
            agent.UpdateSessionConversationId(session, response.ConversationId, cancellationToken);
            await agent.NotifyProvidersOfNewMessagesAsync(session, newRequestMessages, response.Messages, options, cancellationToken).ConfigureAwait(false);
            MarkAsPersisted(newRequestMessages);
            MarkAsPersisted(response.Messages);
        }

        return response;
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var (agent, session) = GetRequiredAgentAndSession();

        List<ChatResponseUpdate> responseUpdates = [];

        IAsyncEnumerator<ChatResponseUpdate> enumerator;
        try
        {
            enumerator = base.GetStreamingResponseAsync(messages, options, cancellationToken).GetAsyncEnumerator(cancellationToken);
        }
        catch (Exception ex)
        {
            var newRequestMessagesOnFailure = GetNewRequestMessages(messages);
            await agent.NotifyProvidersOfFailureAsync(session, ex, newRequestMessagesOnFailure, options, cancellationToken).ConfigureAwait(false);
            throw;
        }

        bool hasUpdates;
        try
        {
            hasUpdates = await enumerator.MoveNextAsync().ConfigureAwait(false);
        }
        catch (Exception ex)
        {
            var newRequestMessagesOnFailure = GetNewRequestMessages(messages);
            await agent.NotifyProvidersOfFailureAsync(session, ex, newRequestMessagesOnFailure, options, cancellationToken).ConfigureAwait(false);
            throw;
        }

        while (hasUpdates)
        {
            var update = enumerator.Current;
            responseUpdates.Add(update);
            yield return update;

            try
            {
                hasUpdates = await enumerator.MoveNextAsync().ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                var newRequestMessagesOnFailure = GetNewRequestMessages(messages);
                await agent.NotifyProvidersOfFailureAsync(session, ex, newRequestMessagesOnFailure, options, cancellationToken).ConfigureAwait(false);
                throw;
            }
        }

        var chatResponse = responseUpdates.ToChatResponse();
        var newRequestMessages = GetNewRequestMessages(messages);

        if (this.ShouldDeferPersistence(options))
        {
            // In mark-only mode or when resuming from a continuation token, just mark messages
            // for later persistence by ChatClientAgent. Conversation ID and provider notification
            // are deferred to end-of-run. For continuation tokens, the end-of-run handler needs
            // to send the combined data from both the previous and current runs.
            MarkAsPersisted(newRequestMessages);
            MarkAsPersisted(chatResponse.Messages);
        }
        else
        {
            // In persist mode, persist immediately and update conversation ID.
            agent.UpdateSessionConversationId(session, chatResponse.ConversationId, cancellationToken);
            await agent.NotifyProvidersOfNewMessagesAsync(session, newRequestMessages, chatResponse.Messages, options, cancellationToken).ConfigureAwait(false);
            MarkAsPersisted(newRequestMessages);
            MarkAsPersisted(chatResponse.Messages);
        }
    }

    /// <summary>
    /// Gets the current <see cref="ChatClientAgent"/> and <see cref="ChatClientAgentSession"/> from the run context.
    /// </summary>
    private static (ChatClientAgent Agent, ChatClientAgentSession Session) GetRequiredAgentAndSession()
    {
        var runContext = AIAgent.CurrentRunContext
            ?? throw new InvalidOperationException(
                $"{nameof(ChatHistoryPersistingChatClient)} can only be used within the context of a running AIAgent. " +
                "Ensure that the chat client is being invoked as part of an AIAgent.RunAsync or AIAgent.RunStreamingAsync call.");

        var chatClientAgent = runContext.Agent.GetService<ChatClientAgent>()
            ?? throw new InvalidOperationException(
                $"{nameof(ChatHistoryPersistingChatClient)} can only be used with a {nameof(ChatClientAgent)}. " +
                $"The current agent is of type '{runContext.Agent.GetType().Name}'.");

        if (runContext.Session is not ChatClientAgentSession chatClientAgentSession)
        {
            throw new InvalidOperationException(
                $"{nameof(ChatHistoryPersistingChatClient)} requires a {nameof(ChatClientAgentSession)}. " +
                $"The current session is of type '{runContext.Session?.GetType().Name ?? "null"}'.");
        }

        return (chatClientAgent, chatClientAgentSession);
    }

    /// <summary>
    /// Determines whether persistence should be deferred to end-of-run instead of happening immediately.
    /// </summary>
    /// <returns>
    /// <see langword="true"/> when in <see cref="MarkOnly"/> mode, when the call is resuming from
    /// a continuation token (since the end-of-run handler needs to combine data from the previous
    /// and current runs), or when background responses are allowed (since the caller may stop
    /// consuming the stream mid-run, preventing the post-stream persistence code from executing).
    /// </returns>
    private bool ShouldDeferPersistence(ChatOptions? options)
    {
        return this.MarkOnly || options?.ContinuationToken is not null || options?.AllowBackgroundResponses is true;
    }

    /// <summary>
    /// Returns only the request messages that have not yet been persisted to chat history.
    /// </summary>
    /// <remarks>
    /// A message is considered already persisted if any of the following is true:
    /// <list type="bullet">
    /// <item>It has the <see cref="PersistedMarkerKey"/> in its <see cref="ChatMessage.AdditionalProperties"/>.</item>
    /// <item>It has an <see cref="AgentRequestMessageSourceType"/> of <see cref="AgentRequestMessageSourceType.ChatHistory"/>
    /// (indicating it was loaded from chat history and does not need to be re-persisted).</item>
    /// <item>It has <see cref="ChatMessage.Contents"/> and all of its <see cref="AIContent"/> items have the
    /// <see cref="PersistedMarkerKey"/> in their <see cref="AIContent.AdditionalProperties"/>. This handles the
    /// streaming case where <see cref="FunctionInvokingChatClient"/> reconstructs <see cref="ChatMessage"/> objects
    /// independently via <c>ToChatResponse()</c>, producing different object references that share the same
    /// underlying <see cref="AIContent"/> instances.</item>
    /// </list>
    /// </remarks>
    /// <returns>A list of request messages that have not yet been persisted.</returns>
    /// <param name="messages">The full set of request messages to filter.</param>
    private static List<ChatMessage> GetNewRequestMessages(IEnumerable<ChatMessage> messages)
    {
        return messages.Where(m => !IsAlreadyPersisted(m)).ToList();
    }

    /// <summary>
    /// Determines whether a message has already been persisted to chat history by this decorator.
    /// </summary>
    private static bool IsAlreadyPersisted(ChatMessage message)
    {
        if (message.AdditionalProperties?.TryGetValue(PersistedMarkerKey, out var value) == true && value is true)
        {
            return true;
        }

        if (message.GetAgentRequestMessageSourceType() == AgentRequestMessageSourceType.ChatHistory)
        {
            return true;
        }

        // In streaming mode, FunctionInvokingChatClient reconstructs ChatMessage objects via ToChatResponse()
        // independently, producing different ChatMessage instances. However, the underlying AIContent objects
        // (e.g., FunctionCallContent, FunctionResultContent) are shared references. Checking for markers on
        // AIContent handles dedup in this case.
        if (message.Contents.Count > 0 && message.Contents.All(c => c.AdditionalProperties?.TryGetValue(PersistedMarkerKey, out var value) == true && value is true))
        {
            return true;
        }

        return false;
    }

    /// <summary>
    /// Marks the given messages as persisted by setting a marker on both the <see cref="ChatMessage"/>
    /// and each of its <see cref="AIContent"/> items.
    /// </summary>
    /// <remarks>
    /// Both levels are marked because <see cref="FunctionInvokingChatClient"/> may reconstruct
    /// <see cref="ChatMessage"/> objects in streaming mode (losing the message-level marker),
    /// but the <see cref="AIContent"/> references are shared and retain their markers.
    /// </remarks>
    /// <param name="messages">The messages to mark as persisted.</param>
    private static void MarkAsPersisted(IEnumerable<ChatMessage> messages)
    {
        foreach (var message in messages)
        {
            message.AdditionalProperties ??= new();
            message.AdditionalProperties[PersistedMarkerKey] = true;

            foreach (var content in message.Contents)
            {
                content.AdditionalProperties ??= new();
                content.AdditionalProperties[PersistedMarkerKey] = true;
            }
        }
    }
}
