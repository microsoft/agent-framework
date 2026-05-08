// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
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
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class MessageInjectingChatClient : DelegatingChatClient
{
    /// <summary>
    /// The key used to store the pending injected messages queue in the session's <see cref="AgentSessionStateBag"/>.
    /// </summary>
    internal const string PendingMessagesStateKey = "MessageInjectingChatClient.PendingInjectedMessages";

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
        var queue = GetOrCreateQueue(session);

        var newMessages = DrainInjectedMessages(queue, messages as IList<ChatMessage> ?? messages.ToList());

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
            bool queueEmpty;
            lock (queue)
            {
                queueEmpty = queue.Count == 0;
            }

            if (queueEmpty)
            {
                return response;
            }

            // Propagate any ConversationId returned by the service so subsequent iterations
            // continue within the same conversation.
            UpdateOptionsForNextIteration(ref options, response.ConversationId);

            newMessages = DrainInjectedMessages(queue, Array.Empty<ChatMessage>());
        }
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(
        IEnumerable<ChatMessage> messages,
        ChatOptions? options = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var session = GetRequiredSession();
        var queue = GetOrCreateQueue(session);

        var newMessages = DrainInjectedMessages(queue, messages as IList<ChatMessage> ?? messages.ToList());

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
            bool queueEmpty;
            lock (queue)
            {
                queueEmpty = queue.Count == 0;
            }

            if (queueEmpty)
            {
                yield break;
            }

            // Propagate any ConversationId returned by the service so subsequent iterations
            // continue within the same conversation.
            UpdateOptionsForNextIteration(ref options, lastConversationId);

            newMessages = DrainInjectedMessages(queue, Array.Empty<ChatMessage>());
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
    public void EnqueueMessages(AgentSession session, IEnumerable<ChatMessage> messages)
    {
        Throw.IfNull(session);
        Throw.IfNull(messages);

        var queue = GetOrCreateQueue(session);

        lock (queue)
        {
            foreach (var message in messages)
            {
                queue.Add(message);
            }
        }
    }

    /// <summary>
    /// Gets or creates the pending injected messages queue from the session's <see cref="AgentSessionStateBag"/>.
    /// </summary>
    private static List<ChatMessage> GetOrCreateQueue(AgentSession session)
    {
        if (session.StateBag.TryGetValue<List<ChatMessage>>(PendingMessagesStateKey, out var queue))
        {
            return queue!;
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
    /// Drains all pending injected messages from the queue and returns a new list combining
    /// the original messages with the drained messages. The original list is never modified.
    /// </summary>
    private static IList<ChatMessage> DrainInjectedMessages(List<ChatMessage> queue, IList<ChatMessage> newMessages)
    {
        lock (queue)
        {
            if (queue.Count == 0)
            {
                return newMessages;
            }

            var combined = new List<ChatMessage>(newMessages);
            combined.AddRange(queue);
            queue.Clear();
            return combined;
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
