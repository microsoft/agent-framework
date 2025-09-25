// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class SendActivityExecutor(SendActivity model, WorkflowFormulaState state) :
    DeclarativeActionExecutor<SendActivity>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (this.Model.Activity is MessageActivityTemplate messageActivity)
        {
            string activityText = this.Engine.Format(messageActivity.Text).Trim();

            await context.AddEventAsync(new MessageActivityEvent(activityText.Trim())).ConfigureAwait(false);
        }

        return default;
    }
}
