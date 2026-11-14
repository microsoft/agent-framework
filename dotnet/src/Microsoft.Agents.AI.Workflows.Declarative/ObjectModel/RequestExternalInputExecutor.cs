// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

[SendsMessage(typeof(ExternalInputRequest))]
[SendsMessage(typeof(ExternalInputResponse))]
internal sealed class RequestExternalInputExecutor(RequestExternalInput model, ResponseAgentProvider agentProvider, WorkflowFormulaState state)
    : DeclarativeActionExecutor<RequestExternalInput>(model, state)
{
    public static class Steps
    {
        public static string Input(string id) => $"{id}_{nameof(Input)}";
        public static string Capture(string id) => $"{id}_{nameof(Capture)}";
    }

    protected override bool IsDiscreteAction => false;
    protected override bool EmitResultEvent => false;

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        ExternalInputRequest inputRequest = new(new AgentResponse());

        await context.SendMessageAsync(inputRequest, cancellationToken).ConfigureAwait(false);

        return default;
    }

    public async ValueTask CaptureResponseAsync(IWorkflowContext context, ExternalInputResponse response, CancellationToken cancellationToken)
    {
        IEnumerable<ChatMessage> capturedMessages = response.Messages;
        string? workflowConversationId = context.GetWorkflowConversation();
        if (workflowConversationId is not null)
        {
            List<ChatMessage> canonicalMessages = [];
            foreach (ChatMessage inputMessage in response.Messages)
            {
                ChatMessage canonicalMessage = await agentProvider.CreateMessageAsync(workflowConversationId, inputMessage, cancellationToken).ConfigureAwait(false);
                canonicalMessages.Add(inputMessage.MergeForLastMessage(canonicalMessage));
            }
            capturedMessages = canonicalMessages;
        }
        ChatMessage? lastMessage = capturedMessages.LastOrDefault();
        if (lastMessage is not null)
        {
            await context.SetLastMessageAsync(lastMessage).ConfigureAwait(false);
        }
        await this.AssignAsync(this.Model.Variable?.Path, capturedMessages.ToTable(), context).ConfigureAwait(false);

        await context.RaiseCompletionEventAsync(this.Model, cancellationToken).ConfigureAwait(false);
    }
}
