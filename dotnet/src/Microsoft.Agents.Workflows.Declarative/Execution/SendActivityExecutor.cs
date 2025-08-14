// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.Workflows.Declarative.Execution;

internal sealed class SendActivityExecutor(SendActivity model) :
    WorkflowActionExecutor<SendActivity>(model)
{
    protected override async ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
    {
        if (this.Model.Activity is MessageActivityTemplate messageActivity)
        {
            StringBuilder templateBuilder = new();
            if (!string.IsNullOrEmpty(messageActivity.Summary))
            {
                templateBuilder.AppendLine($"\t{messageActivity.Summary}");
            }

            string? activityText = this.Context.Engine.Format(messageActivity.Text)?.Trim();
            templateBuilder.AppendLine(activityText + Environment.NewLine);

            await context.AddEventAsync(new DeclarativeWorkflowMessageEvent(new ChatMessage(ChatRole.Assistant, templateBuilder.ToString()))).ConfigureAwait(false);
        }
    }
}
