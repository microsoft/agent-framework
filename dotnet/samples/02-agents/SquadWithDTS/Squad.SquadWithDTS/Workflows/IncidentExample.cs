// Copyright (c) Microsoft. All rights reserved.
using System.Diagnostics;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Squad.SquadWithDTS.Infrastructure;
using Squad.SquadWithDTS.Models;
using Squad.SquadWithDTS.Workflows.Executors;
using Squad.SquadWithDTS.Subsystems;

namespace Squad.SquadWithDTS.Workflows;

/// <summary>
/// Realistic, runnable incident-response orchestration demonstrating:
/// <list type="bullet">
///   <item>AI triage + dynamic subsystem-squad routing (Database / Network / Auth / Payments)</item>
///   <item>Deterministic enrichment (customer lookup, metrics, alert correlation)</item>
///   <item>Mock external communications (customer outreach + third-party status page)</item>
///   <item>Durable execution via the DTS emulator — every executor is checkpointed</item>
///   <item>Diagnose-loop: Squad reviews the full context and can request another enrichment
///         cycle (capped at <see cref="MaxDiagnosisIterations"/> to prevent infinite loops)</item>
/// </list>
/// </summary>
internal static partial class IncidentExample
{
    internal const int MaxDiagnosisIterations = 3;

    /// <summary>
    /// ActivitySource used for all MAF workflow spans emitted by this demo.
    /// Registered with the OTel SDK in <see cref="Program"/> so spans flow to the
    /// Aspire dashboard (or any OTLP-capable backend) when
    /// <c>OTEL_EXPORTER_OTLP_ENDPOINT</c> is set.
    /// </summary>
    internal static readonly ActivitySource DemoActivitySource =
        new("Squad.AgentFramework.Demo", "1.0.0");

    public static async Task<IncidentOrchestrationReport> RunAsync(
        ProviderAgentFactory provider,
        AIAgent squad,
        CancellationToken cancellationToken = default)
    {
        var input          = IncidentEvidence.CreateSyntheticIncidentReport();
        var initialContext = new IncidentWorkflowContext(input);
        var workflow       = BuildWorkflow(provider, squad);

        // DTS endpoint injected by Aspire AppHost via WithEnvironment("DTS_ENDPOINT", ...)
        var dtsEndpoint = Environment.GetEnvironmentVariable("DTS_ENDPOINT")
                          ?? "http://localhost:8080";
        var dtsConnectionString =
            $"Endpoint={dtsEndpoint};TaskHub=default;Authentication=None";

        Console.WriteLine();
        Console.WriteLine("══════════════════════════════════════════════════════════════");
        Console.WriteLine("  Durable Incident-Response Workflow  (DTS-backed)");
        Console.WriteLine($"  Scheduler   : {dtsEndpoint}");
        Console.WriteLine("  DTS UI      : http://localhost:8082");

        var otlpEndpoint = Environment.GetEnvironmentVariable("OTEL_EXPORTER_OTLP_ENDPOINT");
        if (!string.IsNullOrWhiteSpace(otlpEndpoint))
            Console.WriteLine("  Aspire OTel : traces/metrics flowing → Aspire dashboard");
        else
            Console.WriteLine("  Aspire OTel : not configured (set OTEL_EXPORTER_OTLP_ENDPOINT to enable)");

        Console.WriteLine("══════════════════════════════════════════════════════════════");
        Console.WriteLine();

        var host = Host.CreateDefaultBuilder()
            .ConfigureServices(services =>
            {
                services.ConfigureDurableWorkflows(
                    workflowOptions => workflowOptions.AddWorkflow(workflow),
                    workerBuilder: b => b.UseDurableTaskScheduler(dtsConnectionString),
                    clientBuilder: b => b.UseDurableTaskScheduler(dtsConnectionString));
            })
            .Build();

        await host.StartAsync(cancellationToken);

        string? runId = null;
        IncidentWorkflowContext? finalContext = null;

        try
        {
            var workflowClient = host.Services.GetRequiredService<IWorkflowClient>();
            var run = (IAwaitableWorkflowRun)await workflowClient.RunAsync(
                workflow, initialContext, cancellationToken: cancellationToken);

            runId = run.RunId;
            Console.WriteLine($"Workflow run started — run ID: {run.RunId}");
            Console.WriteLine("Watch progress at: http://localhost:8082");
            Console.WriteLine();

            finalContext = await run
                .WaitForCompletionAsync<IncidentWorkflowContext>(cancellationToken);

            Console.WriteLine();
            Console.WriteLine("══════════════════════════════════════════════════════════════");
            Console.WriteLine($"  Workflow complete  |  Status : {finalContext?.DiagnosisStatus}");
            Console.WriteLine($"  Subsystem routed   : {finalContext?.Subsystem}");
            Console.WriteLine($"  Root cause         : {finalContext?.RootCause}");
            Console.WriteLine($"  Diagnosis iters    : {finalContext?.DiagnosisIteration}");
            Console.WriteLine("══════════════════════════════════════════════════════════════");
        }
        finally
        {
            await host.StopAsync(CancellationToken.None);
        }

        return new IncidentOrchestrationReport(
            Example: "incident",
            Status: finalContext is not null ? "PASS" : "INCOMPLETE",
            Provider: provider.Summary,
            Input: input,
            WorkflowRunId: runId,
            FinalContext: finalContext,
            Runtime:
                $"DTS-backed durable workflow | " +
                $"scheduler={dtsEndpoint} | " +
                $"subsystem={finalContext?.Subsystem ?? "unknown"} | " +
                $"iterations={finalContext?.DiagnosisIteration ?? 0}");
    }

    // ── workflow graph construction ───────────────────────────────────────

    private static Workflow BuildWorkflow(ProviderAgentFactory provider, AIAgent squad)
    {
        //
        //   triage
        //     └──► enrich  ◄────────────── loop-back (NeedsMoreInvestigation && iter < Max)
        //            └──► externalComms                                            ▲
        //                   ├──► [Database]     databaseSquad ─┐                  │
        //                   ├──► [Network]      networkSquad  ─┤                  │
        //                   ├──► [Auth]         authSquad     ─┼──► mitigate ──► diagnose
        //                   └──► [Payments]     paymentsSquad ─┘
        //

        var triageExecutor        = new TriageExecutor(squad);
        var enrichExecutor        = new EnrichExecutor();
        var externalCommsExecutor = new ExternalCommsExecutor();
        var databaseSquadExecutor = new DatabaseSquadExecutor(provider);
        var networkSquadExecutor  = new NetworkSquadExecutor(provider);
        var authSquadExecutor     = new AuthSquadExecutor(provider);
        var paymentsSquadExecutor = new PaymentsSquadExecutor(provider);
        var mitigateExecutor      = new MitigateExecutor();
        var diagnoseExecutor      = new DiagnoseExecutor(squad);

        var triageBinding        = triageExecutor.BindExecutor();
        var enrichBinding        = enrichExecutor.BindExecutor();
        var externalCommsBinding = externalCommsExecutor.BindExecutor();
        var databaseBinding      = databaseSquadExecutor.BindExecutor();
        var networkBinding       = networkSquadExecutor.BindExecutor();
        var authBinding          = authSquadExecutor.BindExecutor();
        var paymentsBinding      = paymentsSquadExecutor.BindExecutor();
        var mitigateBinding      = mitigateExecutor.BindExecutor();
        var diagnoseBinding      = diagnoseExecutor.BindExecutor();

        return new WorkflowBuilder(triageBinding)
            .WithName("incident-response")
            .WithDescription(
                "Durable incident-response: AI triage → enrichment → external comms " +
                "→ dynamic subsystem-squad routing → mitigation → diagnose-loop.")
            .WithOpenTelemetry(activitySource: DemoActivitySource)

            // ── forward path ──────────────────────────────────────────────
            .AddEdge(triageBinding, enrichBinding)
            .AddEdge(enrichBinding, externalCommsBinding)

            // ── dynamic subsystem-squad routing (conditional edges) ───────
            .AddEdge<IncidentWorkflowContext>(
                externalCommsBinding, databaseBinding,
                ctx => ctx?.Subsystem == "Database")
            .AddEdge<IncidentWorkflowContext>(
                externalCommsBinding, networkBinding,
                ctx => ctx?.Subsystem == "Network")
            .AddEdge<IncidentWorkflowContext>(
                externalCommsBinding, authBinding,
                ctx => ctx?.Subsystem == "Authentication")
            .AddEdge<IncidentWorkflowContext>(
                externalCommsBinding, paymentsBinding,
                ctx => ctx?.Subsystem == "Payments")

            // ── all subsystem squads converge into mitigate ───────────────
            .AddEdge(databaseBinding, mitigateBinding)
            .AddEdge(networkBinding,  mitigateBinding)
            .AddEdge(authBinding,     mitigateBinding)
            .AddEdge(paymentsBinding, mitigateBinding)

            .AddEdge(mitigateBinding, diagnoseBinding)

            // ── diagnose-loop (loop back to enrich with refined hypothesis) ─
            .AddEdge<IncidentWorkflowContext>(
                diagnoseBinding, enrichBinding,
                ctx => ctx?.DiagnosisStatus == "NeedsMoreInvestigation"
                       && ctx.DiagnosisIteration < MaxDiagnosisIterations)

            .WithOutputFrom(diagnoseBinding)
            .Build();
    }
}
