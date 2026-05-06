// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A delegating chat client that persists chat history and updates session state after each
/// individual service call within the <see cref="FunctionInvokingChatClient"/> loop.
/// </summary>
/// <remarks>
/// <para>
/// This decorator is intended to operate between the <see cref="FunctionInvokingChatClient"/> and the leaf
/// <see cref="IChatClient"/> in a <see cref="ChatClientAgent"/> pipeline. It is activated when
/// <see cref="ChatClientAgentOptions.RequirePerServiceCallChatHistoryPersistence"/> is <see langword="true"/>.
/// </para>
/// <para>
/// When active, it handles two complementary scenarios:
/// </para>
/// <list type="bullet">
/// <item>
/// <term>Framework-managed chat history</term>
/// <description>
/// Before each service call, the decorator loads history from the agent's <see cref="ChatHistoryProvider"/>
/// and prepends it to the request messages. After each successful call, it persists new messages to
/// the provider and returns a sentinel <see cref="ChatOptions.ConversationId"/> so that
/// <see cref="FunctionInvokingChatClient"/> treats the conversation as service-managed — clearing
/// accumulated history between iterations and not injecting duplicate <see cref="FunctionCallContent"/>
/// during approval-response processing.
/// </description>
/// </item>
/// <item>
/// <term>Service-stored chat history</term>
/// <description>
/// When the underlying service manages its own chat history (real <see cref="ChatOptions.ConversationId"/>),
/// the decorator updates <see cref="ChatClientAgentSession.ConversationId"/> after each service call so
/// that intermediate ConversationId changes are captured immediately rather than only at the end of the run.
/// </description>
/// </item>
/// </list>
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
internal sealed class PerServiceCallChatHistoryPersistingChatClient : DelegatingChatClient, IChatMessageInjector
{
    /// <summary>
    /// A sentinel value returned on <see cref="ChatResponse.ConversationId"/> to signal
    /// <see cref="FunctionInvokingChatClient"/> that chat history is being managed downstream.
    /// </summary>
    /// <remarks>
    /// <para>
    /// When <see cref="FunctionInvokingChatClient"/> sees a non-null <see cref="ChatResponse.ConversationId"/>,
    /// it treats the conversation as service-managed: it clears accumulated history between
    /// iterations (via <c>FixupHistories</c>) and does not inject <see cref="FunctionCallContent"/>
    /// into the request during approval-response processing (via <c>ProcessFunctionApprovalResponses</c>).
    /// </para>
    /// <para>
    /// This decorator strips the sentinel from <see cref="ChatOptions.ConversationId"/> on incoming
    /// requests before forwarding to the inner client, so the underlying model never sees it.
    /// </para>
    /// </remarks>
    internal const string LocalHistoryConversationId = "_agent_local_chat_history";

    private readonly ConcurrentQueue<ChatMessage> _pendingInjectedMessages = new();

    /// <summary>
    /// Initializes a new instance of the <see cref="PerServiceCallChatHistoryPersistingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying chat client that will handle the core operations.</param>
    public PerServiceCallChatHistoryPersistingChatClient(IChatClient innerClient)
        : base(innerClient)
    {
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var (agent, session) = GetRequiredAgentAndSession();
        options = StripLocalHistoryConversationId(options);

        bool isServiceManaged = !string.IsNullOrEmpty(options?.ConversationId);
        bool isContinuationOrBackground = options?.ContinuationToken is not null
            || options?.AllowBackgroundResponses is true;
        bool skipSimulation = isServiceManaged || isContinuationOrBackground;

        var newMessages = this.DrainInjectedMessages(messages as IList<ChatMessage> ?? messages.ToList());

        // Loop to process injected messages: after each service call, if no actionable function calls
        // are pending but new messages have been injected into the queue, we call the service again
        // so the model can process them. The loop exits when the response contains actionable
        // function calls (handed off to the parent FunctionInvokingChatClient) or the queue is empty.
        while (true)
        {
            // When simulating, load history and prepend it. When the service manages
            // history (real ConversationId) or this is a continuation/background run,
            // just forward the input messages as-is.
            var messagesForService = skipSimulation
                ? newMessages
                : await agent.LoadChatHistoryAsync(session, newMessages, options, cancellationToken).ConfigureAwait(false);

            ChatResponse response;
            try
            {
                response = await base.GetResponseAsync(messagesForService, options, cancellationToken).ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                await agent.NotifyProvidersOfFailureAsync(session, ex, newMessages, options, cancellationToken).ConfigureAwait(false);
                throw;
            }

            await agent.NotifyProvidersOfNewMessagesAsync(session, newMessages, response.Messages, options, cancellationToken).ConfigureAwait(false);

            if (isContinuationOrBackground)
            {
                // Continuation/background run — the agent's forced end-of-run handles
                // session ConversationId and persistence; the decorator is a no-op.
            }
            else if (isServiceManaged || !string.IsNullOrEmpty(response.ConversationId))
            {
                // Service manages history — update session with the real ConversationId.
                agent.UpdateSessionConversationId(session, response.ConversationId, cancellationToken);
            }
            else
            {
                // Normal simulated path — set sentinel so FICC treats this as service-managed.
                SetSentinelConversationId(response, session);
            }

            // If the response contains actionable function calls, the parent FunctionInvokingChatClient
            // loop will iterate — return immediately so it can process them.
            if (this.HasActionableFunctionCalls(response.Messages))
            {
                return response;
            }

            // No actionable function calls. If there are pending injected messages, loop again
            // to send them to the service. Otherwise, we're done.
            if (this._pendingInjectedMessages.IsEmpty)
            {
                return response;
            }

            newMessages = this.DrainInjectedMessages(Array.Empty<ChatMessage>());
        }
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var (agent, session) = GetRequiredAgentAndSession();
        options = StripLocalHistoryConversationId(options);

        bool isServiceManaged = !string.IsNullOrEmpty(options?.ConversationId);
        bool isContinuationOrBackground = options?.ContinuationToken is not null
            || options?.AllowBackgroundResponses is true;
        bool skipSimulation = isServiceManaged || isContinuationOrBackground;

        var newMessages = this.DrainInjectedMessages(messages as IList<ChatMessage> ?? messages.ToList());

        // Loop to process injected messages: after each service call, if no actionable function calls
        // are pending but new messages have been injected into the queue, we call the service again
        // so the model can process them. The loop exits when the response contains actionable
        // function calls (handed off to the parent FunctionInvokingChatClient) or the queue is empty.
        while (true)
        {
            // When simulating, load history and prepend it. When the service manages
            // history (real ConversationId) or this is a continuation/background run,
            // just forward the input messages as-is.
            var messagesForService = skipSimulation
                ? newMessages
                : await agent.LoadChatHistoryAsync(session, newMessages, options, cancellationToken).ConfigureAwait(false);

            List<ChatResponseUpdate> responseUpdates = [];

            IAsyncEnumerator<ChatResponseUpdate> enumerator;
            try
            {
                enumerator = base.GetStreamingResponseAsync(messagesForService, options, cancellationToken).GetAsyncEnumerator(cancellationToken);
            }
            catch (Exception ex)
            {
                await agent.NotifyProvidersOfFailureAsync(session, ex, newMessages, options, cancellationToken).ConfigureAwait(false);
                throw;
            }

            bool hasUpdates;
            try
            {
                hasUpdates = await enumerator.MoveNextAsync().ConfigureAwait(false);
            }
            catch (Exception ex)
            {
                await agent.NotifyProvidersOfFailureAsync(session, ex, newMessages, options, cancellationToken).ConfigureAwait(false);
                throw;
            }

            while (hasUpdates)
            {
                var update = enumerator.Current;
                responseUpdates.Add(update.Clone());

                // If the service returned a real ConversationId on any update, remember that.
                // Otherwise stamp our sentinel so FICC treats this as service-managed —
                // unless this is a continuation/background run where the agent handles everything.
                if (!string.IsNullOrEmpty(update.ConversationId))
                {
                    isServiceManaged = true;
                }
                else if (!skipSimulation)
                {
                    update.ConversationId = LocalHistoryConversationId;
                }

                yield return update;

                try
                {
                    hasUpdates = await enumerator.MoveNextAsync().ConfigureAwait(false);
                }
                catch (Exception ex)
                {
                    await agent.NotifyProvidersOfFailureAsync(session, ex, newMessages, options, cancellationToken).ConfigureAwait(false);
                    throw;
                }
            }

            var chatResponse = responseUpdates.ToChatResponse();

            await agent.NotifyProvidersOfNewMessagesAsync(session, newMessages, chatResponse.Messages, options, cancellationToken).ConfigureAwait(false);

            if (isContinuationOrBackground)
            {
                // Continuation/background run — the agent's forced end-of-run handles
                // session ConversationId and persistence; the decorator is a no-op.
            }
            else if (isServiceManaged)
            {
                // Service manages history — update session with the real ConversationId.
                agent.UpdateSessionConversationId(session, chatResponse.ConversationId, cancellationToken);
            }
            else
            {
                // Normal simulated path — set sentinel on session.
                session.ConversationId = LocalHistoryConversationId;
            }

            // If the response contains actionable function calls, the parent FunctionInvokingChatClient
            // loop will iterate — return immediately so it can process them.
            if (this.HasActionableFunctionCalls(chatResponse.Messages))
            {
                yield break;
            }

            // No actionable function calls. If there are pending injected messages, loop again
            // to send them to the service. Otherwise, we're done.
            if (this._pendingInjectedMessages.IsEmpty)
            {
                yield break;
            }

            newMessages = this.DrainInjectedMessages(Array.Empty<ChatMessage>());
        }
    }

    /// <inheritdoc/>
    public void EnqueueMessages(IEnumerable<ChatMessage> messages)
    {
        Throw.IfNull(messages);

        foreach (var message in messages)
        {
            this._pendingInjectedMessages.Enqueue(message);
        }
    }

    /// <summary>
    /// Sets the sentinel <see cref="LocalHistoryConversationId"/> on the response and session
    /// so that <see cref="FunctionInvokingChatClient"/> treats the conversation as service-managed.
    /// </summary>
    private static void SetSentinelConversationId(ChatResponse response, ChatClientAgentSession session)
    {
        response.ConversationId = LocalHistoryConversationId;
        session.ConversationId = LocalHistoryConversationId;
    }

    /// <summary>
    /// Gets the current <see cref="ChatClientAgent"/> and <see cref="ChatClientAgentSession"/> from the run context.
    /// </summary>
    private static (ChatClientAgent Agent, ChatClientAgentSession Session) GetRequiredAgentAndSession()
    {
        var runContext = AIAgent.CurrentRunContext
            ?? throw new InvalidOperationException(
                $"{nameof(PerServiceCallChatHistoryPersistingChatClient)} can only be used within the context of a running AIAgent. " +
                "Ensure that the chat client is being invoked as part of an AIAgent.RunAsync or AIAgent.RunStreamingAsync call.");

        var chatClientAgent = runContext.Agent.GetService<ChatClientAgent>()
            ?? throw new InvalidOperationException(
                $"{nameof(PerServiceCallChatHistoryPersistingChatClient)} can only be used with a {nameof(ChatClientAgent)}. " +
                $"The current agent is of type '{runContext.Agent.GetType().Name}'.");

        if (runContext.Session is not ChatClientAgentSession chatClientAgentSession)
        {
            throw new InvalidOperationException(
                $"{nameof(PerServiceCallChatHistoryPersistingChatClient)} requires a {nameof(ChatClientAgentSession)}. " +
                $"The current session is of type '{runContext.Session?.GetType().Name ?? "null"}'.");
        }

        return (chatClientAgent, chatClientAgentSession);
    }

    /// <summary>
    /// If the <paramref name="options"/> carry the <see cref="LocalHistoryConversationId"/> sentinel,
    /// returns a clone with the conversation ID cleared so the inner client never sees it.
    /// Otherwise returns the original <paramref name="options"/> unchanged.
    /// </summary>
    private static ChatOptions? StripLocalHistoryConversationId(ChatOptions? options)
    {
        if (options?.ConversationId == LocalHistoryConversationId)
        {
            options = options.Clone();
            options.ConversationId = null;
        }

        return options;
    }

    /// <summary>
    /// Drains all pending injected messages from the queue and returns a new list combining
    /// the original messages with the drained messages. The original list is never modified.
    /// </summary>
    private IList<ChatMessage> DrainInjectedMessages(IList<ChatMessage> newMessages)
    {
        if (this._pendingInjectedMessages.IsEmpty)
        {
            return newMessages;
        }

        var combined = new List<ChatMessage>(newMessages);

        while (this._pendingInjectedMessages.TryDequeue(out var message))
        {
            combined.Add(message);
        }

        return combined;
    }

    /// <summary>
    /// Determines whether any message in the response contains a <see cref="FunctionCallContent"/>
    /// that is not marked as <see cref="FunctionCallContent.InformationalOnly"/>.
    /// </summary>
    private bool HasActionableFunctionCalls(IList<ChatMessage> responseMessages)
    {
        for (int i = 0; i < responseMessages.Count; i++)
        {
            var contents = responseMessages[i].Contents;
            for (int j = 0; j < contents.Count; j++)
            {
                if (contents[j] is FunctionCallContent fcc && !fcc.InformationalOnly)
                {
                    return true;
                }
            }
        }

        return false;
    }
}
