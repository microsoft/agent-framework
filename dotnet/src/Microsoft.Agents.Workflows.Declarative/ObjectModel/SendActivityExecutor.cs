// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.Declarative.ObjectModel;

internal sealed class SendActivityExecutor(SendActivity model, DeclarativeWorkflowState state) :
    DeclarativeActionExecutor<SendActivity>(model, state)
{
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

            AgentRunResponse response = new([new ChatMessage(ChatRole.Assistant, templateBuilder.ToString().Trim())]);
            await context.AddEventAsync(new AgentRunResponseEvent(this.Id, response)).ConfigureAwait(false);
        }

        return default;
    }
}
