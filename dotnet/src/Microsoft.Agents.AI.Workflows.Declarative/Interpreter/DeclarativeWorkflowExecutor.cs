// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Interpreter;

/// <summary>
/// The root executor for a declarative workflow.
/// </summary>
/// <remarks>
/// In addition to the strongly-typed <typeparamref name="TInput"/> route inherited from
/// <see cref="Executor{TInput}"/>, this executor also accepts <see cref="string"/>,
/// <see cref="ChatMessage"/>, <see cref="IEnumerable{T}"/> of <see cref="ChatMessage"/>,
/// <see cref="ChatMessage"/><c>[]</c>, and <see cref="TurnToken"/> so that the workflow
/// satisfies <see cref="ChatProtocolExtensions.IsChatProtocol"/>. This makes the workflow
/// usable both for direct <c>Run.SendMessageAsync(input)</c> invocations and for hosting
/// via <see cref="WorkflowHostingExtensions.AsAIAgent(Workflow, string?, string?, string?, IWorkflowExecutionEnvironment?, bool, bool)"/>.
///
/// <para>
/// Each non-<see cref="TurnToken"/> input drives the declarative graph forward
/// immediately. The host's <see cref="TurnToken"/> arrives after the message batch and
/// is treated as a no-op because the inbound message has already been processed.
/// External responses (HITL function results) bypass the start executor entirely
/// (they are routed via <c>WorkflowSession.SendResponseAsync</c> to request-info
/// executors), so the start executor only ever sees a single inbound batch per turn.
/// </para>
/// </remarks>
internal sealed class DeclarativeWorkflowExecutor<TInput>(
    string workflowId,
    DeclarativeWorkflowOptions options,
    WorkflowFormulaState state,
    Func<TInput, ChatMessage> inputTransform) :
    Executor<TInput>(workflowId), IResettableExecutor, IModeledAction where TInput : notnull
{
    /// <inheritdoc/>
    public ValueTask ResetAsync()
    {
        return default;
    }

    /// <inheritdoc/>
    [SendsMessage(typeof(ActionExecutorResult))]
    public override ValueTask HandleAsync(TInput message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        ChatMessage input = inputTransform.Invoke(message);
        return this.AdvanceAsync(input, context, cancellationToken);
    }

    /// <inheritdoc/>
    protected override ProtocolBuilder ConfigureProtocol(ProtocolBuilder protocolBuilder)
    {
        // Inherit the TInput route + method/class attributes (e.g. SendsMessage on HandleAsync).
        ProtocolBuilder result = base.ConfigureProtocol(protocolBuilder);

        // Add the chat-protocol input shapes so the workflow satisfies IsChatProtocol
        // and can be hosted via AsAIAgent. Skip any shape that already matches TInput
        // (the inherited route handles that case via inputTransform).
        return result.ConfigureRoutes(this.ConfigureChatProtocolRoutes)
                     .SendsMessage<ActionExecutorResult>();
    }

    private void ConfigureChatProtocolRoutes(RouteBuilder routeBuilder)
    {
        Type tInput = typeof(TInput);

        // Use IsAssignableFrom rather than exact equality so that a broader TInput (e.g.
        // object or an interface that already accepts ChatMessage) does not get its
        // inherited inputTransform shadowed by a more-specific handler we register here.
        if (!tInput.IsAssignableFrom(typeof(string)))
        {
            routeBuilder.AddHandler<string>(this.HandleStringAsync);
        }

        if (!tInput.IsAssignableFrom(typeof(ChatMessage)))
        {
            routeBuilder.AddHandler<ChatMessage>(this.HandleChatMessageAsync);
        }

        if (!tInput.IsAssignableFrom(typeof(IEnumerable<ChatMessage>)))
        {
            routeBuilder.AddHandler<IEnumerable<ChatMessage>>(this.HandleChatMessagesAsync);
        }

        if (!tInput.IsAssignableFrom(typeof(ChatMessage[])))
        {
            routeBuilder.AddHandler<ChatMessage[]>(this.HandleChatMessageArrayAsync);
        }

        routeBuilder.AddHandler<TurnToken>(this.HandleTurnTokenAsync);
    }

    private ValueTask HandleStringAsync(string message, IWorkflowContext context, CancellationToken cancellationToken)
    {
        return this.AdvanceAsync(new ChatMessage(ChatRole.User, message), context, cancellationToken);
    }

    private ValueTask HandleChatMessageAsync(ChatMessage message, IWorkflowContext context, CancellationToken cancellationToken)
    {
        return this.AdvanceAsync(message, context, cancellationToken);
    }
    private async ValueTask HandleChatMessagesAsync(IEnumerable<ChatMessage> messages, IWorkflowContext context, CancellationToken cancellationToken)
    {
        var list = messages as IList<ChatMessage> ?? new List<ChatMessage>(messages);
        if (list.Count == 0)
        {
            return;
        }

        for (int i = 0; i < list.Count; i++)
        {
            await this.AdvanceAsync(list[i], context, cancellationToken, finalizeTurn: i == list.Count - 1).ConfigureAwait(false);
        }
    }

    private async ValueTask HandleChatMessageArrayAsync(ChatMessage[] messages, IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (messages.Length == 0)
        {
            return;
        }

        for (int i = 0; i < messages.Length; i++)
        {
            await this.AdvanceAsync(messages[i], context, cancellationToken, finalizeTurn: i == messages.Length - 1).ConfigureAwait(false);
        }
    }

    // The host sends a TurnToken after the message batch; the message has already
    // driven the graph forward, so we treat the token as a no-op here.
    private ValueTask HandleTurnTokenAsync(TurnToken token, IWorkflowContext context, CancellationToken cancellationToken)
    {
        return default;
    }

    private async ValueTask AdvanceAsync(ChatMessage input, IWorkflowContext context, CancellationToken cancellationToken, bool finalizeTurn = true)
    {
        // No state to restore if we're starting from the beginning.
        state.SetInitialized();

        DeclarativeWorkflowContext declarativeContext = new(context, state);

        // Conversation id resolution prefers state already persisted by a prior turn,
        // so multi-turn invocations reuse the same backend conversation rather than
        // creating a fresh one each turn.
        string? conversationId = declarativeContext.GetWorkflowConversation();
        if (string.IsNullOrWhiteSpace(conversationId))
        {
            conversationId = options.ConversationId;
        }

        bool conversationCreated = false;
        if (string.IsNullOrWhiteSpace(conversationId))
        {
            conversationId = await options.AgentProvider.CreateConversationAsync(cancellationToken).ConfigureAwait(false);
            conversationCreated = true;
        }

        if (conversationCreated || !string.Equals(declarativeContext.GetWorkflowConversation(), conversationId, StringComparison.Ordinal))
        {
            await declarativeContext.QueueConversationUpdateAsync(conversationId!, isExternal: true, cancellationToken).ConfigureAwait(false);
        }

        ChatMessage inputMessage = await options.AgentProvider.CreateMessageAsync(conversationId!, input, cancellationToken).ConfigureAwait(false);

        // Use the original input for System.LastMessage to ensure Text is preserved (the
        // service may strip text on round-trip), but substitute server-side media references
        // (e.g., HostedFileContent) so subsequent actions don't re-upload large blobs.
        await declarativeContext.SetLastMessageAsync(input.MergeForLastMessage(inputMessage)).ConfigureAwait(false);

        if (finalizeTurn)
        {
            await context.SendResultMessageAsync(this.Id, cancellationToken).ConfigureAwait(false);
        }
    }
}
