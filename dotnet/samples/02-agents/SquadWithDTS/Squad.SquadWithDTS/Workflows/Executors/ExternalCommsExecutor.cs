// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI.Workflows;
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Workflows.Executors;

/// <summary>
/// Mock external communications: simulates customer outreach and third-party
/// status page checks. No AI calls — purely deterministic.
/// </summary>
internal sealed class ExternalCommsExecutor
    : Executor<IncidentWorkflowContext, IncidentWorkflowContext>("ExternalComms")
{
    public override async ValueTask<IncidentWorkflowContext> HandleAsync(
        IncidentWorkflowContext ctx,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        var outreachTask = MockServices.MockCustomerOutreachService.NotifyCustomerAsync(
            ctx.Customer!, ctx.Report, cancellationToken);
        var statusTask = MockServices.MockThirdPartyStatusService.GetStatusPageSummaryAsync(
            cancellationToken);

        await Task.WhenAll(outreachTask, statusTask);

        return ctx with
        {
            ExternalCommsResult =
                $"Customer notified: {outreachTask.Result} | " +
                $"Third-party status: {statusTask.Result}",
        };
    }
}
