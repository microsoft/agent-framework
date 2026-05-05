// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;

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

            // Route through YieldOutputAsync so the activity participates in the workflow's
            // output-filter pipeline. The runner currently special-cases AgentResponse to
            // produce an AgentResponseEvent identical to the one we'd build by hand, so this
            // is behavior-preserving today and forward-compatible if filtering is ever
            // applied to agent responses.
            AgentResponse response = new([new ChatMessage(ChatRole.Assistant, activityText)]);
            await context.YieldOutputAsync(response, cancellationToken).ConfigureAwait(false);
        }

        return default;
    }
}
