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
internal sealed class PerServiceCallChatHistoryPersistingChatClient : DelegatingChatClient
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

        var newMessages = messages as IList<ChatMessage> ?? messages.ToList();

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

        return response;
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

        // Snapshot the input messages into a private list. The caller (typically
        // FunctionInvokingChatClient) reuses a single mutable buffer across iterations,
        // and the streaming path can defer persistence until after the caller has already
        // mutated that buffer for the next iteration (e.g. on the catch-path
        // PersistInputOnErrorAsync). Aliasing the caller's list would then cause us to
        // persist the wrong messages — losing FunctionResultContent and corrupting
        // history with dangling FunctionCallContent.
        var newMessages = messages.ToList();

        // When simulating, load history and prepend it. When the service manages
        // history (real ConversationId) or this is a continuation/background run,
        // just forward the input messages as-is.
        var messagesForService = skipSimulation
            ? (IEnumerable<ChatMessage>)newMessages
            : await agent.LoadChatHistoryAsync(session, newMessages, options, cancellationToken).ConfigureAwait(false);

        List<ChatResponseUpdate> responseUpdates = [];

        IAsyncEnumerator<ChatResponseUpdate> enumerator;
        try
        {
            enumerator = base.GetStreamingResponseAsync(messagesForService, options, cancellationToken).GetAsyncEnumerator(cancellationToken);
        }
        catch (Exception ex)
        {
            // The service call could not even be initiated. Persist the input messages
            // (e.g. function results from a prior iteration) so that history remains
            // consistent and a subsequent run does not see dangling FunctionCallContent.
            await PersistInputOnErrorAsync(agent, session, newMessages, options, cancellationToken).ConfigureAwait(false);
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
            await PersistInputOnErrorAsync(agent, session, newMessages, options, cancellationToken).ConfigureAwait(false);
            await agent.NotifyProvidersOfFailureAsync(session, ex, newMessages, options, cancellationToken).ConfigureAwait(false);
            throw;
        }

        bool loopExitedNormally = false;
        try
        {
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
                    await PersistInputOnErrorAsync(agent, session, newMessages, options, cancellationToken).ConfigureAwait(false);
                    await agent.NotifyProvidersOfFailureAsync(session, ex, newMessages, options, cancellationToken).ConfigureAwait(false);
                    throw;
                }
            }
            loopExitedNormally = true;
        }
        finally
        {
            // If the iterator was disposed early (e.g. consumer bailed out, or the underlying
            // stream ended without throwing but the loop did not complete normally), we still
            // need to persist the input messages — otherwise function-call/function-result
            // pairings can be lost, leaving the next iteration with dangling FunctionCallContent.
            if (!loopExitedNormally)
            {
                try
                {
                    await PersistInputOnErrorAsync(agent, session, newMessages, options, CancellationToken.None).ConfigureAwait(false);
                }
                catch
                {
                    // Best-effort persistence on the abnormal-exit path; swallow to avoid masking the original error.
                }
            }
        }

        var chatResponse = responseUpdates.ToChatResponse();

        // If the service emitted an in-stream error (e.g. rate limit) the underlying client
        // may complete the enumeration "normally" while leaving us with no usable assistant
        // output. Treat that as a failure and persist the input messages without polluting
        // history with the error content.
        var inStreamError = chatResponse.Messages
            .SelectMany(m => m.Contents)
            .OfType<ErrorContent>()
            .FirstOrDefault();

        if (inStreamError is not null)
        {
            await PersistInputOnErrorAsync(agent, session, newMessages, options, cancellationToken).ConfigureAwait(false);
            var errorMessage = string.IsNullOrWhiteSpace(inStreamError.Message)
                ? "The chat service returned an in-stream error."
                : inStreamError.Message;
            var streamException = new InvalidOperationException(errorMessage);
            await agent.NotifyProvidersOfFailureAsync(session, streamException, newMessages, options, cancellationToken).ConfigureAwait(false);
            throw streamException;
        }

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
    }

    /// <summary>
    /// Persists the input messages (the new messages handed to this iteration, e.g.
    /// <see cref="FunctionResultContent"/> entries from the previous iteration) to the
    /// agent's chat history without any response messages. This is used on error paths
    /// to ensure that function-call/function-result pairings are not split across
    /// failures, which would otherwise leave dangling <see cref="FunctionCallContent"/>
    /// in the persisted chat history and corrupt subsequent runs.
    /// </summary>
    private static async Task PersistInputOnErrorAsync(
        ChatClientAgent agent,
        ChatClientAgentSession session,
        List<ChatMessage> newMessages,
        ChatOptions? options,
        CancellationToken cancellationToken)
    {
        if (newMessages.Count == 0)
        {
            return;
        }

        await agent.NotifyProvidersOfNewMessagesAsync(session, newMessages, [], options, cancellationToken).ConfigureAwait(false);
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
}
