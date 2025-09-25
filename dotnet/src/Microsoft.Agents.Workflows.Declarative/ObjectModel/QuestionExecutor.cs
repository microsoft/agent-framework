// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Entities;
using Microsoft.Agents.Workflows.Declarative.Events;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class QuestionExecutor(Question model, WorkflowFormulaState state) :
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

    public static bool IsComplete(object? message)
    {
        ExecutorResultMessage executorMessage = ExecutorResultMessage.ThrowIfNot(message);
        return executorMessage.Result is null;
    }

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
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
            await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);
        }

        return default;
    }

    public async ValueTask PrepareResponseAsync(IWorkflowContext context, ExecutorResultMessage message, CancellationToken cancellationToken)
    {
        int count = await this._promptCount.ReadAsync(context).ConfigureAwait(false);
        InputRequest inputRequest = new(this.FormatPrompt(this.Model.Prompt));
        await context.SendMessageAsync(inputRequest).ConfigureAwait(false);
        await this._promptCount.WriteAsync(context, count + 1).ConfigureAwait(false);
    }

    public async ValueTask CaptureResponseAsync(IWorkflowContext context, InputResponse message, CancellationToken cancellationToken)
    {
        FormulaValue? extractedValue = null;
        if (string.IsNullOrWhiteSpace(message.Value))
        {
            string unrecognizedResponse = this.FormatPrompt(this.Model.UnrecognizedPrompt);
            await context.AddEventAsync(new MessageActivityEvent(unrecognizedResponse.Trim())).ConfigureAwait(false);
        }
        else
        {
            EntityExtractionResult entityResult = EntityExtractor.Parse(this.Model.Entity, message.Value);
            if (entityResult.IsValid)
            {
                extractedValue = entityResult.Value;
            }
            else
            {
                string invalidResponse = this.FormatPrompt(this.Model.InvalidPrompt);
                await context.AddEventAsync(new MessageActivityEvent(invalidResponse.Trim())).ConfigureAwait(false);
            }
        }

        if (extractedValue is null)
        {
            await this.PromptAsync(context, cancellationToken).ConfigureAwait(false);
        }
        else
        {
            await this.AssignAsync(this.Model.Variable?.Path, extractedValue, context).ConfigureAwait(false);
            await this._hasExecuted.WriteAsync(context, true).ConfigureAwait(false);
            await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);
        }
    }

    public async ValueTask CompleteAsync(IWorkflowContext context, ExecutorResultMessage message, CancellationToken cancellationToken)
    {
        await context.RaiseCompletionEventAsync(this.Model).ConfigureAwait(false);
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
            await context.AddEventAsync(new MessageActivityEvent(defaultValueResponse.Trim())).ConfigureAwait(false);
            await context.SendResultMessageAsync(this.Id, result: null, cancellationToken).ConfigureAwait(false);
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
