// Copyright (c) Microsoft. All rights reserved.

using System;
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

            string responseId = Guid.NewGuid().ToString("N");
            string messageId = Guid.NewGuid().ToString("N");
            ChatMessage message = new(ChatRole.Assistant, activityText) { MessageId = messageId };

            // Emit an AgentResponseUpdateEvent so chat protocols (e.g. AsAIAgent) receive the
            // activity text as streaming chat content. This event is yielded by WorkflowSession
            // unconditionally, mirroring how AgentProviderExtensions surfaces autoSend agent
            // updates — without it, SendActivity output is dropped whenever the host runs with
            // includeWorkflowOutputsInResponse = false (the default).
            AgentResponseUpdate update =
                new(ChatRole.Assistant, activityText)
                {
                    AuthorName = this.Id,
                    MessageId = messageId,
                    ResponseId = responseId,
                };
            await context.AddEventAsync(new AgentResponseUpdateEvent(this.Id, update), cancellationToken).ConfigureAwait(false);

            // Route through YieldOutputAsync so the activity participates in the workflow's
            // output-filter pipeline. The runner currently special-cases AgentResponse to
            // produce an AgentResponseEvent identical to the one we'd build by hand, which
            // is the gated summary surfaced only when includeWorkflowOutputsInResponse = true.
            AgentResponse response = new([message]) { ResponseId = responseId };
            await context.YieldOutputAsync(response, cancellationToken).ConfigureAwait(false);
        }

        return default;
    }
}
