// Copyright (c) Microsoft. All rights reserved.
using System.Text.Json;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using OpenTelemetry;
using OpenTelemetry.Metrics;
using OpenTelemetry.Resources;
using OpenTelemetry.Trace;
using Squad.SquadWithDTS.Agents;
using Squad.SquadWithDTS.Examples;
using Squad.SquadWithDTS.Infrastructure;
using Squad.SquadWithDTS.Workflows;

// ── Build host ────────────────────────────────────────────────────────────────
var builder = Host.CreateApplicationBuilder(args);
builder.Configuration.AddEnvironmentVariables();

// ── OpenTelemetry ─────────────────────────────────────────────────────────────
var otlpEndpoint = builder.Configuration["OTEL_EXPORTER_OTLP_ENDPOINT"];
if (!string.IsNullOrWhiteSpace(otlpEndpoint))
{
    builder.Services
        .AddOpenTelemetry()
        .ConfigureResource(r => r.AddService("Squad.SquadWithDTS"))
        .WithTracing(t => t
            .AddSource("Squad.AgentFramework.SquadAgent")
            .AddSource("Squad.AgentFramework.Demo")
            .AddHttpClientInstrumentation()
            .AddOtlpExporter(o => o.Endpoint = new Uri(otlpEndpoint)))
        .WithMetrics(m => m
            .AddMeter("Squad.AgentFramework.SquadAgent")
            .AddRuntimeInstrumentation()
            .AddOtlpExporter(o => o.Endpoint = new Uri(otlpEndpoint)));
}

// ── Services ──────────────────────────────────────────────────────────────────
builder.Services.AddSingleton<SquadAgent>();
builder.Services.AddSingleton<ProviderAgentFactory>(sp =>
    new ProviderAgentFactory(
        sp.GetRequiredService<IConfiguration>(),
        sp.GetRequiredService<SquadAgent>()));

var host = builder.Build();

// ── Run ───────────────────────────────────────────────────────────────────────
var config  = host.Services.GetRequiredService<IConfiguration>();
var squad   = host.Services.GetRequiredService<SquadAgent>();
var factory = host.Services.GetRequiredService<ProviderAgentFactory>();

// Resolve example: CLI arg --example <name>, env SQUAD_AF_EXAMPLE, or interactive prompt
var example = args.SkipWhile(a => a != "--example").Skip(1).FirstOrDefault()
           ?? config["SQUAD_AF_EXAMPLE"]
           ?? PromptForExample();

Console.WriteLine($"Running example: {example}");
Console.WriteLine($"Provider: {factory.Summary.Provider} | Backed: {factory.Summary.IsProviderBacked}");

using var cts = new CancellationTokenSource();
Console.CancelKeyPress += (_, e) => { e.Cancel = true; cts.Cancel(); };

await host.StartAsync(cts.Token);

try
{
    switch (example.ToLowerInvariant())
    {
        case "incident":
            var report = await IncidentExample.RunAsync(factory, squad, cts.Token);
            Console.WriteLine();
            Console.WriteLine("Final report:");
            Console.WriteLine(JsonSerializer.Serialize(report, new JsonSerializerOptions { WriteIndented = true }));
            break;

        case "squad-as-agent":
            await SquadAsAgentExample.RunAsync(factory, squad, cts.Token);
            break;

        case "workflow":
            await WorkflowExample.RunAsync(factory, squad, cts.Token);
            break;

        default:
            Console.WriteLine($"Unknown example '{example}'. Valid: incident, squad-as-agent, workflow");
            break;
    }
}
finally
{
    await host.StopAsync(CancellationToken.None);
    if (squad is IAsyncDisposable d) await d.DisposeAsync();
}

// ── helpers ───────────────────────────────────────────────────────────────────
static string PromptForExample()
{
    Console.WriteLine();
    Console.WriteLine("Select example to run:");
    Console.WriteLine("  1  incident       (DTS-backed durable workflow — requires Docker)");
    Console.WriteLine("  2  squad-as-agent (SquadAgent as plain MAF participant)");
    Console.WriteLine("  3  workflow        (Sequential in-process workflow)");
    Console.Write("Choice [1]: ");
    return (Console.ReadLine()?.Trim() ?? "1") switch
    {
        "2" => "squad-as-agent",
        "3" => "workflow",
        _   => "incident",
    };
}
