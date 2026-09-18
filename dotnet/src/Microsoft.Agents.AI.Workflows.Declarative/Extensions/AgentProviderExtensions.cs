// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class AgentProviderExtensions
{
    public static async ValueTask<AgentResponse> InvokeAgentAsync(
        this ResponseAgentProvider agentProvider,
        string executorId,
        IWorkflowContext context,
        string agentName,
        string? conversationId,
        bool autoSend,
        IEnumerable<ChatMessage>? inputMessages = null,
        IDictionary<string, object?>? inputArguments = null,
        CancellationToken cancellationToken = default)
    {
        IAsyncEnumerable<AgentResponseUpdate> agentUpdates = agentProvider.InvokeAgentAsync(agentName, null, conversationId, inputMessages, inputArguments, cancellationToken);

        // Foundry managed workflows treat responses produced on the workflow conversation
        // as workflow output even when autoSend is explicitly false. Preserve that direct-run
        // contract here. Workflow.AsAIAgent separately removes matching streamed/completed
        // message duplicates at its hosting boundary.
        bool isWorkflowConversation = context.IsWorkflowConversation(conversationId, out string? workflowConversationId);
        autoSend |= isWorkflowConversation;

        // Assign stable IDs to content-bearing chat updates before emitting and aggregating them.
        // Contentless updates may carry only metadata and must not become empty messages.
        List<AgentResponseUpdate> updates = [];
        string? generatedMessageId = null;
        string? generatedMessageResponseId = null;
        ChatRole? generatedMessageRole = null;
        await foreach (AgentResponseUpdate update in agentUpdates.ConfigureAwait(false))
        {
            await AssignConversationIdAsync((update.RawRepresentation as ChatResponseUpdate)?.ConversationId).ConfigureAwait(false);

            if (string.IsNullOrWhiteSpace(update.MessageId))
            {
                bool hasContent =
                    update.Contents.Any(
                        content => content is not TextContent textContent || !string.IsNullOrEmpty(textContent.Text));
                if (hasContent)
                {
                    if (generatedMessageId is null
                        || (generatedMessageResponseId is not null
                            && update.ResponseId is not null
                            && !string.Equals(generatedMessageResponseId, update.ResponseId, StringComparison.Ordinal))
                        || (generatedMessageRole is not null
                            && update.Role is not null
                            && generatedMessageRole != update.Role))
                    {
                        generatedMessageId = Guid.NewGuid().ToString("N");
                    }

                    generatedMessageResponseId = update.ResponseId ?? generatedMessageResponseId;
                    generatedMessageRole = update.Role ?? generatedMessageRole;
                    update.MessageId = generatedMessageId;
                    if (update.RawRepresentation is ChatResponseUpdate rawUpdate)
                    {
                        rawUpdate.MessageId = generatedMessageId;
                    }
                }
            }
            else
            {
                generatedMessageId = null;
                generatedMessageResponseId = null;
                generatedMessageRole = null;
            }

            updates.Add(update);

            // Error updates are withheld: they reach the client verbatim, bypassing the host's
            // exception-detail policy. The detail still arrives via the thrown exception.
            if (autoSend && !HasError(update))
            {
                await context.AddEventAsync(new AgentResponseUpdateEvent(executorId, update), cancellationToken).ConfigureAwait(false);
            }
        }

        AgentResponse response = updates.ToAgentResponse();

        // Fail before the response is announced as completed or copied to the conversation.
        ThrowIfFailed(response, agentName);

        if (autoSend)
        {
            await context.AddEventAsync(new AgentResponseEvent(executorId, response), cancellationToken).ConfigureAwait(false);
        }

        // If autoSend is enabled and this is not the workflow conversation, copy messages to the workflow conversation.
        if (autoSend && !isWorkflowConversation && workflowConversationId is not null)
        {
            foreach (ChatMessage message in response.Messages)
            {
                await agentProvider.CreateMessageAsync(workflowConversationId, message, cancellationToken).ConfigureAwait(false);
            }
        }

        return response;

        async ValueTask AssignConversationIdAsync(string? assignValue)
        {
            if (assignValue is not null && conversationId is null)
            {
                conversationId = assignValue;

                await context.QueueConversationUpdateAsync(conversationId, cancellationToken).ConfigureAwait(false);
            }
        }
    }

    /// <summary>
    /// Indicates whether an update carries an agent error rather than usable content.
    /// </summary>
    private static bool HasError(AgentResponseUpdate update) =>
        update.Contents.Any(content => content is ErrorContent);

    /// <summary>
    /// Fails the action when the agent reported an error rather than a usable response.
    /// </summary>
    /// <remarks>
    /// Any top-level <see cref="ErrorContent"/> is a failure, covering both a failed run and a
    /// refusal, and excluding <c>incomplete</c>, which carries partial content instead. The detail
    /// is folded into the exception so one error path stays under the host's exception-detail policy.
    /// </remarks>
    private static void ThrowIfFailed(AgentResponse response, string agentName)
    {
        // The last error wins: a run that fails without detail yields a generic placeholder first,
        // and the specific cause follows as its own error.
        ErrorContent? error =
            response.Messages
                .SelectMany(message => message.Contents)
                .OfType<ErrorContent>()
                .LastOrDefault();

        if (error is null)
        {
            return;
        }

        string errorCode = string.IsNullOrWhiteSpace(error.ErrorCode) ? "unknown" : error.ErrorCode!;
        string errorMessage = string.IsNullOrWhiteSpace(error.Message) ? "No error message was provided." : error.Message!;

        // No inner exception: DeclarativeActionException is unwrapped to its inner exception when
        // reported, which would discard this message.
        throw new DeclarativeActionException($"Agent '{agentName}' failed [{errorCode}]: {errorMessage}");
    }
}
