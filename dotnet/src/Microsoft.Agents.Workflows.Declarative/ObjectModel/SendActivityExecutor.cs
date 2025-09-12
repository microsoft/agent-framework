// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class SendActivityExecutor(SendActivity model, DeclarativeWorkflowState state) :
    DeclarativeActionExecutor<SendActivity>(model, state)
{
    public readonly Guid _check = Guid.NewGuid();

    protected override async ValueTask<object?> ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (this.Model.Activity is MessageActivityTemplate messageActivity)
        {
            StringBuilder templateBuilder = new();
            if (!string.IsNullOrEmpty(messageActivity.Summary))
            {
                templateBuilder.AppendLine($"\t{messageActivity.Summary}");
            }

            string? activityText = this.State.Format(messageActivity.Text)?.Trim();
            templateBuilder.AppendLine(activityText);

            await context.AddEventAsync(new MessageActivityEvent(templateBuilder.ToString().Trim())).ConfigureAwait(false);
        }

        return default;
    }
}
