// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class QuestionExecutor(Question model, DeclarativeWorkflowState state) :
    DeclarativeActionExecutor<Question>(model, state)
{
    protected override bool EmitResultEvent => false;

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        // QUESTION
        //this.Model.Variable; // VARIABLEPATH
        //this.Model.Entity; // ENTITYREFERENCE

        //this.Model.Prompt;  // PROMPT
        //this.Model.InvalidPrompt; // PROMPT
        //this.Model.DefaultValueResponse; // PROMPT

        //this.Model.DefaultValue; //VALUE
        //this.Model.AlwaysPrompt; // BOOL
        //this.Model.SkipQuestionMode; // ENUM
        //this.Model.HoldSettings; // ABSTRACT

        //// INPUTDIALOG
        //this.Model.RepeatCount; // INT
        //this.Model.InterruptionPolicy; // SEALED
        //this.Model.UnrecognizedPrompt; // PROMPT

        //this.State.Format(this.Model.Prompt) // %%% TEMPLATEBASE

        await context.SendMessageAsync("REQUEST").ConfigureAwait(false);

        return default;
    }

    public async ValueTask HandleResponseAsync(IWorkflowContext context, object? message, CancellationToken cancellationToken)
    {
        await this.AssignAsync(this.Model.Variable?.Path, message.ToFormula(), context).ConfigureAwait(false);
    }
}
