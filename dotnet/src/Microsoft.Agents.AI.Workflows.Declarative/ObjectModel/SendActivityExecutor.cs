// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.AI.Workflows.Declarative.ObjectModel;

internal sealed class SendActivityExecutor(SendActivity model, WorkflowFormulaState state) :
    DeclarativeActionExecutor<SendActivity>(model, state)
{
    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        if (this.Model.Activity is MessageActivityTemplate messageActivity)
        {
            string activityText = this.Engine.Format(messageActivity.Text).Trim();

            await context.AddEventAsync(new MessageActivityEvent(activityText.Trim()), cancellationToken).ConfigureAwait(false);
        }

        return default;
    }
}
