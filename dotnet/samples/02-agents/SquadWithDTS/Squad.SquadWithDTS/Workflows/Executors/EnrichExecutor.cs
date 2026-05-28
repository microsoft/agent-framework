// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI.Workflows;
using Squad.SquadWithDTS.Infrastructure;
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Workflows.Executors;

/// <summary>
/// Deterministic enrichment: fetches customer info, metrics window, and
/// recent alert correlations in parallel. No AI calls.
/// </summary>
internal sealed class EnrichExecutor
    : Executor<IncidentWorkflowContext, IncidentWorkflowContext>("Enrich")
{
    public override async ValueTask<IncidentWorkflowContext> HandleAsync(
        IncidentWorkflowContext ctx,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        var customerTask = MockServices.MockCustomerService.GetCustomerAsync(
            ctx.Report.CustomerId, cancellationToken);
        var metricsTask = MockServices.MockMetricsService.GetMetricsWindowAsync(
            ctx.Report.Region, cancellationToken);
        var alertsTask = MockServices.MockAlertCorrelationService.GetRecentAlertsAsync(
            ctx.Report.Region, cancellationToken);

        await Task.WhenAll(customerTask, metricsTask, alertsTask);

        return ctx with
        {
            Customer     = customerTask.Result,
            Metrics      = metricsTask.Result,
            RecentAlerts = alertsTask.Result,
            // Carry forward any refined hypothesis from a diagnose-loop iteration
            Hypothesis   = ctx.RefinedHypothesis ?? ctx.Hypothesis,
        };
    }
}
