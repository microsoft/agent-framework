// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Entities;
using Microsoft.Agents.AI.Workflows.Declarative.Events;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class QuestionExecutor(Question model, WorkflowAgentProvider agentProvider, WorkflowFormulaState state) :
    DeclarativeActionExecutor<Question>(model, state)
{
    public static class Steps
    {
        public static string Prepare(string id) => $"{id}_{nameof(Prepare)}";
        public static string Input(string id) => $"{id}_{nameof(Input)}";
        public static string Capture(string id) => $"{id}_{nameof(Capture)}";
    }

    private readonly DurableProperty<int> _promptCount = new(nameof(_promptCount));
    private readonly DurableProperty<bool> _hasExecuted = new(nameof(_hasExecuted));

    protected override bool IsDiscreteAction => false;
    protected override bool EmitResultEvent => false;

    // Input has been captured when Result is null
    public static bool IsComplete(object? message)
    {
        ActionExecutorResult executorMessage = ActionExecutorResult.ThrowIfNot(message);
        return executorMessage.Result is null;
    }

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        await this._promptCount.WriteAsync(context, 0).ConfigureAwait(false);

        InitializablePropertyPath variable = Throw.IfNull(this.Model.Variable);
        bool hasValue = context.ReadState(variable.Path) is BlankValue;
        bool alwaysPrompt = this.Evaluator.GetValue(this.Model.AlwaysPrompt).Value;

        bool proceed = !alwaysPrompt || hasValue;
        if (proceed)
        {
            SkipQuestionMode mode = this.Evaluator.GetValue(this.Model.SkipQuestionMode).Value;
            proceed =
                mode switch
                {
                    SkipQuestionMode.SkipOnFirstExecutionIfVariableHasValue => !await this._hasExecuted.ReadAsync(context).ConfigureAwait(false),
                    SkipQuestionMode.AlwaysSkipIfVariableHasValue => hasValue,
                    SkipQuestionMode.AlwaysAsk => true,
                    _ => true,
                };
        }

        if (proceed)
        {
            await this.PromptAsync(context, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            await context.SendResultMessageAsync(this.Id, cancellationToken).ConfigureAwait(false);
        }

        return default;
    }

    public async ValueTask PrepareResponseAsync(IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken)
    {
        int count = await this._promptCount.ReadAsync(context).ConfigureAwait(false);
        InputRequest inputRequest = new(this.FormatPrompt(this.Model.Prompt));
        await context.SendMessageAsync(inputRequest, targetId: null, cancellationToken).ConfigureAwait(false);
        await this._promptCount.WriteAsync(context, count + 1).ConfigureAwait(false);
    }

    public async ValueTask CaptureResponseAsync(IWorkflowContext context, InputResponse message, CancellationToken cancellationToken)
    {
        FormulaValue? extractedValue = null;
        if (message.Value is null)
        {
            string unrecognizedResponse = this.FormatPrompt(this.Model.UnrecognizedPrompt);
            await context.AddEventAsync(new MessageActivityEvent(unrecognizedResponse.Trim()), cancellationToken).ConfigureAwait(false);
        }
        else
        {
            EntityExtractionResult entityResult = EntityExtractor.Parse(this.Model.Entity, message.Value.Text);
            if (entityResult.IsValid)
            {
                extractedValue = entityResult.Value;
            }
            else
            {
                string invalidResponse = this.Model.InvalidPrompt is not null ? this.FormatPrompt(this.Model.InvalidPrompt) : "Invalid response";
                await context.AddEventAsync(new MessageActivityEvent(invalidResponse.Trim()), cancellationToken).ConfigureAwait(false);
            }
        }

        if (extractedValue is null)
        {
            await this.PromptAsync(context, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            bool autoSend = true;

            if (this.Model.ExtensionData?.Properties.TryGetValue("autoSend", out DataValue? autoSendValue) ?? false)
            {
                autoSend = autoSendValue.ToObject() is bool value && value;
            }

            if (autoSend)
            {
                string? workflowConversationId = context.GetWorkflowConversation();
                if (workflowConversationId is not null)
                {
                    // Input message always defined if values has been extracted.
                    ChatMessage input = message.Value!;
                    await agentProvider.CreateMessageAsync(workflowConversationId, input, cancellationToken).ConfigureAwait(false);
                    await context.SetLastMessageAsync(input).ConfigureAwait(false);
                }
            }

            await this.AssignAsync(this.Model.Variable?.Path, extractedValue, context).ConfigureAwait(false);
            await this._hasExecuted.WriteAsync(context, true).ConfigureAwait(false);
            await context.SendResultMessageAsync(this.Id, cancellationToken).ConfigureAwait(false);
        }
    }

    public async ValueTask CompleteAsync(IWorkflowContext context, ActionExecutorResult message, CancellationToken cancellationToken)
    {
        await context.RaiseCompletionEventAsync(this.Model, cancellationToken).ConfigureAwait(false);
    }

    private async ValueTask PromptAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        long repeatCount = this.Evaluator.GetValue(this.Model.RepeatCount).Value;
        int actualCount = await this._promptCount.ReadAsync(context).ConfigureAwait(false);
        if (actualCount >= repeatCount)
        {
            ValueExpression defaultValueExpression = Throw.IfNull(this.Model.DefaultValue);
            DataValue defaultValue = this.Evaluator.GetValue(defaultValueExpression).Value;
            await this.AssignAsync(this.Model.Variable?.Path, defaultValue.ToFormula(), context).ConfigureAwait(false);
            string defaultValueResponse = this.FormatPrompt(this.Model.DefaultValueResponse);
            await context.AddEventAsync(new MessageActivityEvent(defaultValueResponse.Trim()), cancellationToken).ConfigureAwait(false);
            await context.SendResultMessageAsync(this.Id, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            await context.SendResultMessageAsync(this.Id, result: true, cancellationToken).ConfigureAwait(false);
        }
    }

    private string FormatPrompt(ActivityTemplateBase? promptTemplate)
    {
        if (promptTemplate is not MessageActivityTemplate messageActivity)
        {
            return string.Empty;
        }

        return this.Engine.Format(messageActivity.Text).Trim();
    }
}
