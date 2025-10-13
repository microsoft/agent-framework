// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class InvokeAzureAgentExecutor(InvokeAzureAgent model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<InvokeAzureAgent>(model, state)
{
    public static class Steps
    {
        public static string Input(string id) => $"{id}_{nameof(Input)}";
        public static string Resume(string id) => $"{id}_{nameof(Resume)}";
    }

    // Input is requested by a message other than ActionExecutorResult.
    public static bool RequiresInput(object? message) => message is not ActionExecutorResult;

    private AzureAgentUsage AgentUsage => Throw.IfNull(this.Model.Agent, $"{nameof(this.Model)}.{nameof(this.Model.Agent)}");
    private AzureAgentInput? AgentInput => this.Model.Input;
    private AzureAgentOutput? AgentOutput => this.Model.Output;

    protected override bool EmitResultEvent => false;
    protected override bool IsDiscreteAction => false;

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await this.InvokeAgentAsync(context, this.GetInputMessages(), cancellationToken).ConfigureAwait(false);

        return default;
    }

    public ValueTask ResumeAsync(IWorkflowContext context, AgentToolResponse message, CancellationToken cancellationToken) =>
        // %%% FUNCTION: AUTO EXECUTE EXISTING FUNCTIONS
        this.InvokeAgentAsync(context, [new ChatMessage(ChatRole.Tool, [.. message.FunctionResults])], cancellationToken);

    public async ValueTask CompleteAsync(IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken)
    {
        await context.RaiseCompletionEventAsync(this.Model, cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask InvokeAgentAsync(IWorkflowContext context, IEnumerable<ChatMessage>? messages, CancellationToken cancellationToken)
    {
        string? conversationId = this.GetConversationId();
        string agentName = this.GetAgentName();
        string? additionalInstructions = this.GetAdditionalInstructions();
        bool autoSend = this.GetAutoSendValue();

        bool isComplete;
        AgentRunResponse agentResponse;
        do
        {
            agentResponse = await agentProvider.InvokeAgentAsync(this.Id, context, agentName, conversationId, autoSend, additionalInstructions, messages, cancellationToken).ConfigureAwait(false);

            isComplete = true;
            if (string.IsNullOrEmpty(agentResponse.Text))
            {
                IEnumerable<FunctionCallContent> toolCallsSequential = agentResponse.Messages.SelectMany(m => m.Contents.OfType<FunctionCallContent>());
                HashSet<string> pendingToolCalls = [];
                List<(FunctionCallContent, AIFunction)> availableTools = [];
#pragma warning disable CA1851 // %%% PRAGMA COLLECTION: Possible multiple enumerations of 'IEnumerable' collection
                foreach (FunctionCallContent functionCall in toolCallsSequential)
                {
                    if (agentProvider.TryGetFunctionTool(functionCall.Name, out AIFunction? functionTool))
                    {
                        availableTools.Add((functionCall, functionTool));
                    }
                    else
                    {
                        pendingToolCalls.Add(functionCall.CallId);
                    }
                }

                isComplete = pendingToolCalls.Count == 0;

                if (isComplete && availableTools.Count > 0) // %%% FUNCTION: isComplete = false => INVOKE LATER WHEN RESULTS RETURNED
                {
                    // All tools are available, invoke them.
                    IList<FunctionResultContent> functionResults = await InvokeToolsAsync(availableTools, cancellationToken).ConfigureAwait(false);
                    messages = [new ChatMessage(ChatRole.Tool, [.. functionResults])]; // %%% FUNCTION: DRY !!!
                    isComplete = false;
                }

                if (pendingToolCalls.Count > 0)
                {
                    Dictionary<string, FunctionCallContent> toolCalls = toolCallsSequential.ToDictionary(tool => tool.CallId);
                    AgentToolRequest toolRequest =
                        new(agentName,
                            toolCalls
                                .Where(toolCall => pendingToolCalls.Contains(toolCall.Value.CallId))
                                .Select(toolCall => toolCall.Value));
                    await context.SendMessageAsync(toolRequest, targetId: null, cancellationToken).ConfigureAwait(false);
                    isComplete = false;
                    break;
                }
#pragma warning restore CA1851
            }
        }
        while (!isComplete);

        if (isComplete)
        {
            await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);
        }

        await this.AssignAsync(this.AgentOutput?.Messages?.Path, agentResponse.Messages.ToTable(), context).ConfigureAwait(false);
    }

    private static async ValueTask<IList<FunctionResultContent>> InvokeToolsAsync(IEnumerable<(FunctionCallContent, AIFunction)> functionCalls, CancellationToken cancellationToken) // %%% FUNCTION: DRY !!!
    {
        List<FunctionResultContent> results = [];
        foreach ((FunctionCallContent functionCall, AIFunction functionTool) in functionCalls) // %%% PARALLEL
        {
            AIFunctionArguments functionArguments = new(functionCall.Arguments); // %%% FUNCTION: PORTABLE
            if (functionArguments.Count > 0)
            {
                functionArguments = new(new Dictionary<string, object?>() { { "menuItem", "Clam Chowder" } });
            }
            object? result = await functionTool.InvokeAsync(functionArguments, cancellationToken).ConfigureAwait(false); // %%% MEAI COMMON ???
#pragma warning disable IL2026 // %%% PRAGMA JSON: Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access otherwise can break functionality when trimming application code
#pragma warning disable IL3050 // %%% PRAGMA JSON: Calling members annotated with 'RequiresDynamicCodeAttribute' may break functionality when AOT compiling.
            results.Add(new FunctionResultContent(functionCall.CallId, JsonSerializer.Serialize(result))); // %%% JSON CONVERSION
#pragma warning restore IL3050
#pragma warning restore IL2026
        }
        return results;
    }

    private IEnumerable<ChatMessage>? GetInputMessages()
    {
        DataValue? userInput = null;

        if (this.AgentInput?.Messages is not null)
        {
            EvaluationResult<DataValue> expressionResult = this.Evaluator.GetValue(this.AgentInput.Messages);
            userInput = expressionResult.Value;
        }

        return userInput?.ToChatMessages();
    }

    private string? GetConversationId()
    {
        if (this.Model.ConversationId is null)
        {
            return null;
        }

        EvaluationResult<string> conversationIdResult = this.Evaluator.GetValue(this.Model.ConversationId);
        return conversationIdResult.Value.Length == 0 ? null : conversationIdResult.Value;
    }

    private string GetAgentName() =>
        this.Evaluator.GetValue(
            Throw.IfNull(
                this.AgentUsage.Name,
                $"{nameof(this.Model)}.{nameof(this.Model.Agent)}.{nameof(this.Model.Agent.Name)}")).Value;

    private string? GetAdditionalInstructions()
    {
        string? additionalInstructions = null;

        if (this.AgentInput?.AdditionalInstructions is not null)
        {
            additionalInstructions = this.Engine.Format(this.AgentInput.AdditionalInstructions);
        }

        return additionalInstructions;
    }

    private bool GetAutoSendValue()
    {
        if (this.AgentOutput?.AutoSend is null)
        {
            return true;
        }

        EvaluationResult<bool> autoSendResult = this.Evaluator.GetValue(this.AgentOutput.AutoSend);

        return autoSendResult.Value;
    }
}
