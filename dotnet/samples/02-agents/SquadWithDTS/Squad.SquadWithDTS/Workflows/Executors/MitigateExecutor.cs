// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI.Workflows;
using Squad.SquadWithDTS.Models;

namespace Squad.SquadWithDTS.Workflows.Executors;

/// <summary>
/// Deterministic mitigation lookup: maps subsystem + triage hypothesis to
/// a set of read-only investigative actions. No AI calls.
/// </summary>
internal sealed class MitigateExecutor
    : Executor<IncidentWorkflowContext, IncidentWorkflowContext>("Mitigate")
{
    private static readonly Dictionary<string, string[]> MitigationPlaybook = new(
        StringComparer.OrdinalIgnoreCase)
    {
        ["Database"] =
        [
            "Query pg_stat_activity for long-running queries (> 30 s)",
            "Check connection pool saturation: SHOW max_connections; SELECT count(*) FROM pg_stat_activity;",
            "Inspect deadlock logs: grep 'deadlock' /var/log/postgresql/postgresql.log | tail -50",
            "Review slow query log for the past 15 minutes",
            "Verify index health: SELECT schemaname, tablename, indexname FROM pg_indexes WHERE tablename='orders';",
        ],
        ["Network"] =
        [
            "Ping external dependencies from the affected region",
            "Check DNS resolution for payment-gateway endpoint",
            "Inspect load balancer health: review target group health in AWS/Azure console",
            "Review network ACL and security group rules for recent changes",
            "Capture tcpdump sample: sudo tcpdump -i eth0 port 443 -c 100",
        ],
        ["Authentication"] =
        [
            "Check token expiry and clock skew across service pods",
            "Review auth service error rate: kubectl logs -l app=auth-service --tail=100",
            "Verify OAuth2 provider status: check identity provider dashboard",
            "Rotate affected service account credentials if compromise suspected",
            "Review recent changes to RBAC policies",
        ],
        ["Payments"] =
        [
            "Verify payment gateway status page for active incidents",
            "Check retry queue depth: inspect dead-letter queue in message broker",
            "Review idempotency key collisions in payment processor logs",
            "Confirm PCI compliance controls are intact before further investigation",
            "Escalate to payments team if gateway SLA > 10 min",
        ],
    };

    public override async ValueTask<IncidentWorkflowContext> HandleAsync(
        IncidentWorkflowContext ctx,
        IWorkflowContext context,
        CancellationToken cancellationToken = default)
    {
        await Task.Yield(); // keep async contract

        var subsystem = ctx.Subsystem ?? "Database";
        var steps = MitigationPlaybook.TryGetValue(subsystem, out var playbook)
            ? string.Join("\n", playbook.Select((s, i) => $"  {i + 1}. {s}"))
            : "No playbook found — escalate to on-call engineer.";

        return ctx with { MitigationSteps = steps };
    }
}
