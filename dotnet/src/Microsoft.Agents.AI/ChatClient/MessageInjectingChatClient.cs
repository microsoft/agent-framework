// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A delegating chat client that supports injecting messages into the function execution loop.
/// </summary>
/// <remarks>
/// <para>
/// This decorator enables external code (such as tool delegates) to enqueue messages that will be
/// sent to the underlying model at the next opportunity. It sits between the <see cref="FunctionInvokingChatClient"/>
/// and the <see cref="PerServiceCallChatHistoryPersistingChatClient"/> (or the leaf <see cref="IChatClient"/>)
/// in a <see cref="ChatClientAgent"/> pipeline.
/// </para>
/// <para>
/// The injected messages queue is stored per-session in the <see cref="AgentSession.StateBag"/>, ensuring
/// isolation between concurrent sessions.
/// </para>
/// <para>
/// After each service call, if no actionable <see cref="FunctionCallContent"/> is returned but injected
/// messages are pending, the decorator loops internally and calls the inner client again with the new
/// messages. When actionable function calls are present, control returns to the parent
/// <see cref="FunctionInvokingChatClient"/> loop.
/// </para>
/// <para>
/// This chat client must be used within the context of a running <see cref="ChatClientAgent"/>. It retrieves the
/// current session from <see cref="AIAgent.CurrentRunContext"/>, which is set automatically when an agent's
/// <see cref="AIAgent.RunAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/> or
/// <see cref="AIAgent.RunStreamingAsync(IEnumerable{ChatMessage}, AgentSession?, AgentRunOptions?, CancellationToken)"/>
/// method is called.
/// </para>
/// </remarks>
public sealed class MessageInjectingChatClient : DelegatingChatClient
{
    /// <summary>
    /// The key used to store the pending injected messages queue in the session's <see cref="AgentSessionStateBag"/>.
    /// </summary>
    internal const string PendingMessagesStateKey = "MessageInjectingChatClient.PendingInjectedMessages";

    /// <summary>
    /// Per-session semaphore used to serialize all access to a session's pending messages queue,
    /// including its creation. A single client instance is shared across sessions, so the lock is
    /// keyed on the session and stored in a <see cref="ConditionalWeakTable{TKey, TValue}"/> so it
    /// is released automatically when the session is collected.
    /// </summary>
    private readonly ConditionalWeakTable<AgentSession, SemaphoreSlim> _sessionLocks = new();

    /// <summary>
    /// Initializes a new instance of the <see cref="MessageInjectingChatClient"/> class.
    /// </summary>
    /// <param name="innerClient">The underlying chat client that will handle the core operations.</param>
    public MessageInjectingChatClient(IChatClient innerClient)
        : base(innerClient)
    {
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        CancellationToken cancellationToken = default)
    {
        var session = GetRequiredSession();

        var newMessages = await this.DrainInjectedMessagesAsync(session, messages as IList<ChatMessage> ?? messages.ToList(), cancellationToken).ConfigureAwait(false);

        // Loop to process injected messages: after each service call, if no actionable function calls
        // are pending but new messages have been injected into the queue, we call the service again
        // so the model can process them. The loop exits when the response contains actionable
        // function calls (handed off to the parent FunctionInvokingChatClient) or the queue is empty.
        while (true)
        {
            var response = await base.GetResponseAsync(newMessages, options, cancellationToken).ConfigureAwait(false);

            // If the response contains actionable function calls, the parent FunctionInvokingChatClient
            // loop will iterate — return immediately so it can process them.
            if (HasActionableFunctionCalls(response.Messages))
            {
                return response;
            }

            // No actionable function calls. If there are pending injected messages, loop again
            // to send them to the service. Otherwise, we're done.
            if (await this.IsQueueEmptyAsync(session, cancellationToken).ConfigureAwait(false))
            {
                return response;
            }

            // Propagate any ConversationId returned by the service so subsequent iterations
            // continue within the same conversation.
            UpdateOptionsForNextIteration(ref options, response.ConversationId);

            newMessages = await this.DrainInjectedMessagesAsync(session, Array.Empty<ChatMessage>(), cancellationToken).ConfigureAwait(false);
        }
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var session = GetRequiredSession();

        var newMessages = await this.DrainInjectedMessagesAsync(session, messages as IList<ChatMessage> ?? messages.ToList(), cancellationToken).ConfigureAwait(false);

        // Loop to process injected messages: after each service call, if no actionable function calls
        // are pending but new messages have been injected into the queue, we call the service again
        // so the model can process them. The loop exits when the response contains actionable
        // function calls (handed off to the parent FunctionInvokingChatClient) or the queue is empty.
        while (true)
        {
            bool hasActionableFunctionCalls = false;
            string? lastConversationId = null;

            var enumerator = base.GetStreamingResponseAsync(newMessages, options, cancellationToken).GetAsyncEnumerator(cancellationToken);
            try
            {
                while (await enumerator.MoveNextAsync().ConfigureAwait(false))
                {
                    var update = enumerator.Current;

                    // Check each update for actionable function call content as it streams through.
                    if (!hasActionableFunctionCalls && HasActionableFunctionCalls(update))
                    {
                        hasActionableFunctionCalls = true;
                    }

                    // Track the latest ConversationId from the stream.
                    if (update.ConversationId is not null)
                    {
                        lastConversationId = update.ConversationId;
                    }

                    yield return update;
                }
            }
            finally
            {
                await enumerator.DisposeAsync().ConfigureAwait(false);
            }

            // If the response contains actionable function calls, the parent FunctionInvokingChatClient
            // loop will iterate — return immediately so it can process them.
            if (hasActionableFunctionCalls)
            {
                yield break;
            }

            // No actionable function calls. If there are pending injected messages, loop again
            // to send them to the service. Otherwise, we're done.
            if (await this.IsQueueEmptyAsync(session, cancellationToken).ConfigureAwait(false))
            {
                yield break;
            }

            // Propagate any ConversationId returned by the service so subsequent iterations
            // continue within the same conversation.
            UpdateOptionsForNextIteration(ref options, lastConversationId);

            newMessages = await this.DrainInjectedMessagesAsync(session, Array.Empty<ChatMessage>(), cancellationToken).ConfigureAwait(false);
        }
    }

    /// <summary>
    /// Enqueues one or more messages to be used at the next opportunity.
    /// </summary>
    /// <remarks>
    /// This method is thread-safe and can be called concurrently from tool delegates or other code
    /// while the function execution loop is in progress. The enqueued messages will be picked up
    /// at the next opportunity.
    /// </remarks>
    /// <param name="session">The agent session to enqueue messages for.</param>
    /// <param name="messages">The messages to enqueue.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A <see cref="Task"/> that represents the asynchronous operation.</returns>
    public async Task EnqueueMessagesAsync(AgentSession session, IEnumerable<ChatMessage> messages, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(session);
        Throw.IfNull(messages);

        SemaphoreSlim sessionLock = this.GetSessionLock(session);
        await sessionLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var queue = GetOrCreateQueue(session);
            foreach (var message in messages)
            {
                queue.Add(message);
            }
        }
        finally
        {
            sessionLock.Release();
        }
    }

    /// <summary>
    /// Gets a snapshot of the pending injected messages for the specified session.
    /// </summary>
    /// <remarks>
    /// Returns a copy of the current pending messages that have not yet been consumed by the
    /// injection loop. This can be used to display pending messages to the user. The returned
    /// list is a point-in-time snapshot; messages may be consumed between calls.
    /// </remarks>
    /// <param name="session">The agent session to check.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests.</param>
    /// <returns>A read-only list of pending messages, or an empty list if none are pending.</returns>
    public async Task<IReadOnlyList<ChatMessage>> GetPendingMessagesAsync(AgentSession session, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(session);

        SemaphoreSlim sessionLock = this.GetSessionLock(session);
        await sessionLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            if (!session.StateBag.TryGetValue<List<ChatMessage>>(PendingMessagesStateKey, out var queue) || queue is null || queue.Count == 0)
            {
                return Array.Empty<ChatMessage>();
            }

            return queue.ToList();
        }
        finally
        {
            sessionLock.Release();
        }
    }

    /// <summary>
    /// Returns the per-session semaphore used to serialize access to the session's pending messages queue.
    /// </summary>
    private SemaphoreSlim GetSessionLock(AgentSession session)
        => this._sessionLocks.GetValue(session, static _ => new SemaphoreSlim(1, 1));

    /// <summary>
    /// Gets or creates the pending injected messages queue from the session's <see cref="AgentSessionStateBag"/>.
    /// </summary>
    /// <remarks>
    /// Callers must hold the session lock (see <see cref="GetSessionLock"/>) while calling this method and
    /// while operating on the returned queue, since the get-or-create is a non-atomic check-then-act.
    /// </remarks>
    private static List<ChatMessage> GetOrCreateQueue(AgentSession session)
    {
        if (session.StateBag.TryGetValue<List<ChatMessage>>(PendingMessagesStateKey, out var queue) && queue is not null)
        {
            return queue;
        }

        var newQueue = new List<ChatMessage>();
        session.StateBag.SetValue(PendingMessagesStateKey, newQueue);
        return newQueue;
    }

    /// <summary>
    /// Gets the current <see cref="AgentSession"/> from the run context.
    /// </summary>
    private static AgentSession GetRequiredSession()
    {
        var runContext = AIAgent.CurrentRunContext
            ?? throw new InvalidOperationException(
                $"{nameof(MessageInjectingChatClient)} can only be used within the context of a running AIAgent. " +
                "Ensure that the chat client is being invoked as part of an AIAgent.RunAsync or AIAgent.RunStreamingAsync call.");

        return runContext.Session
            ?? throw new InvalidOperationException(
                $"{nameof(MessageInjectingChatClient)} requires a session. " +
                "The current run context does not have a session.");
    }

    /// <summary>
    /// Returns <see langword="true"/> if the session's pending messages queue is empty or has not been created.
    /// </summary>
    private async Task<bool> IsQueueEmptyAsync(AgentSession session, CancellationToken cancellationToken)
    {
        SemaphoreSlim sessionLock = this.GetSessionLock(session);
        await sessionLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            return !session.StateBag.TryGetValue<List<ChatMessage>>(PendingMessagesStateKey, out var queue) || queue is null || queue.Count == 0;
        }
        finally
        {
            sessionLock.Release();
        }
    }

    /// <summary>
    /// Drains all pending injected messages from the session's queue and returns a new list combining
    /// the original messages with the drained messages. The original <paramref name="newMessages"/> list
    /// is never modified.
    /// </summary>
    private async Task<IList<ChatMessage>> DrainInjectedMessagesAsync(AgentSession session, IList<ChatMessage> newMessages, CancellationToken cancellationToken)
    {
        SemaphoreSlim sessionLock = this.GetSessionLock(session);
        await sessionLock.WaitAsync(cancellationToken).ConfigureAwait(false);
        try
        {
            var queue = GetOrCreateQueue(session);
            if (queue.Count == 0)
            {
                return newMessages;
            }

            var combined = new List<ChatMessage>(newMessages);
            combined.AddRange(queue);
            queue.Clear();
            return combined;
        }
        finally
        {
            sessionLock.Release();
        }
    }

    /// <summary>
    /// Determines whether any message in the list contains a <see cref="FunctionCallContent"/>
    /// that is not marked as <see cref="FunctionCallContent.InformationalOnly"/>.
    /// </summary>
    private static bool HasActionableFunctionCalls(IList<ChatMessage> responseMessages)
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

    /// <summary>
    /// Determines whether a streaming update contains a <see cref="FunctionCallContent"/>
    /// that is not marked as <see cref="FunctionCallContent.InformationalOnly"/>.
    /// </summary>
    private static bool HasActionableFunctionCalls(ChatResponseUpdate update)
    {
        var contents = update.Contents;
        for (int i = 0; i < contents.Count; i++)
        {
            if (contents[i] is FunctionCallContent fcc && !fcc.InformationalOnly)
            {
                return true;
            }
        }

        return false;
    }

    /// <summary>
    /// Propagates the <paramref name="conversationId"/> from the service response into
    /// <paramref name="options"/> so that subsequent loop iterations continue within the
    /// same conversation. Clones <paramref name="options"/> before mutating to avoid
    /// affecting the caller's instance.
    /// </summary>
    private static void UpdateOptionsForNextIteration(ref ChatOptions? options, string? conversationId)
    {
        if (options is null)
        {
            if (conversationId is not null)
            {
                options = new() { ConversationId = conversationId };
            }
        }
        else if (options.ConversationId != conversationId)
        {
            options = options.Clone();
            options.ConversationId = conversationId;
        }
    }
}
