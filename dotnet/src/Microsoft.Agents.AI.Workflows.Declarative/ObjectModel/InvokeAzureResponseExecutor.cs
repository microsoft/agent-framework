// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

#pragma warning disable CS9113 // %%% REMOVE
internal sealed class InvokeAzureResponseExecutor(InvokeAzureResponse model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<InvokeAzureResponse>(model, state)
{
    public static class Steps
    {
        public static string UserInput(string id) => $"{id}_{nameof(UserInput)}";
        public static string FunctionTool(string id) => $"{id}_{nameof(FunctionTool)}";
        public static string Resume(string id) => $"{id}_{nameof(Resume)}";
    }

    public static bool RequiresFunctionCall(object? message) => message is AgentFunctionToolRequest;

    public static bool RequiresUserInput(object? message) => message is UserInputRequest;

    public static bool RequiresNothing(object? message) => message is ActionExecutorResult;

    //private GptComponentMetadata AgentUsage => Throw.IfNull(this.Model.Agent, $"{nameof(this.Model)}.{nameof(this.Model.Agent)}");
    //private AzureAgentInput? AgentInput => this.Model.Input;
    //private AzureAgentOutput? AgentOutput => this.Model.Output;

    protected override bool EmitResultEvent => false;
    protected override bool IsDiscreteAction => false;

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        //await this.InvokeAgentAsync(context, this.GetInputMessages(), cancellationToken).ConfigureAwait(false);

        return default;
    }

    public ValueTask ResumeAsync(IWorkflowContext context, AgentFunctionToolResponse message, CancellationToken cancellationToken) =>
        this.InvokeAgentAsync(context, [message.FunctionResults.ToChatMessage()], cancellationToken);

    public async ValueTask CompleteAsync(IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken)
    {
        await context.RaiseCompletionEventAsync(this.Model, cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask InvokeAgentAsync(IWorkflowContext context, IEnumerable<ChatMessage>? messages, CancellationToken cancellationToken)
    {
        //string? conversationId = this.GetConversationId();
        //bool autoSend = this.GetAutoSendValue();

        //bool isComplete = true;

        //AgentRunResponse agentResponse = await agentProvider.InvokeAgentAsync(this.Id, context, agentName, conversationId, autoSend, messages, cancellationToken).ConfigureAwait(false);

        //if (string.IsNullOrEmpty(agentResponse.Text))
        //{
        //    // Identify function calls that have no associated result.
        //    List<UserInputRequestContent> inputRequests = GetUserInputRequests(agentResponse);
        //    if (inputRequests.Count > 0)
        //    {
        //        isComplete = false;
        //        UserInputRequest approvalRequest = new(agentName, inputRequests.OfType<AIContent>().ToArray());
        //        await context.SendMessageAsync(approvalRequest, cancellationToken).ConfigureAwait(false);
        //    }

        //    // Identify function calls that have no associated result.
        //    List<FunctionCallContent> functionCalls = GetOrphanedFunctionCalls(agentResponse);
        //    if (functionCalls.Count > 0)
        //    {
        //        isComplete = false;
        //        AgentFunctionToolRequest toolRequest = new(agentName, functionCalls);
        //        await context.SendMessageAsync(toolRequest, cancellationToken).ConfigureAwait(false);
        //    }
        //}

        //if (isComplete)
        //{
        //    await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);
        //}

        //await this.AssignAsync(this.AgentOutput?.Messages?.Path, agentResponse.Messages.ToTable(), context).ConfigureAwait(false);
    }
}
