// Copyright (c) Microsoft. All rights reserved.
using System.Diagnostics;
using System.Diagnostics.Metrics;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.GitHub.Copilot;
using Microsoft.Extensions.Configuration;

namespace Squad.SquadWithDTS.Agents;

/// <summary>
/// Wraps <see cref="GitHubCopilotAgent"/> as a first-class MAF <see cref="AIAgent"/>.
/// Emits OTel spans and metrics so that every agent run appears in the Aspire dashboard
/// (and any OTLP-compatible back-end) when <c>OTEL_EXPORTER_OTLP_ENDPOINT</c> is set.
/// </summary>
public sealed class SquadAgent : AIAgent, IAsyncDisposable
{
    private static readonly ActivitySource SquadActivitySource =
        new("Squad.AgentFramework.SquadAgent", "1.0.0");

    private static readonly Meter SquadMeter = new("Squad.AgentFramework.SquadAgent", "1.0.0");
    private static readonly Counter<long>   RunsStartedCounter   = SquadMeter.CreateCounter<long>("squad_agent.runs_started");
    private static readonly Counter<long>   RunsCompletedCounter = SquadMeter.CreateCounter<long>("squad_agent.runs_completed");
    private static readonly Counter<long>   SessionsCreated      = SquadMeter.CreateCounter<long>("squad_agent.sessions_created");
    private static readonly Histogram<double> RunDurationMs      = SquadMeter.CreateHistogram<double>("squad_agent.run_duration_ms");

    private readonly GitHubCopilotAgent _inner;
    private readonly string _agentId;

    public SquadAgent(IConfiguration configuration)
    {
        var opts = configuration
            .GetSection("SquadAgent")
            .Get<SquadAgentOptions>() ?? new SquadAgentOptions();

        _agentId = opts.AgentId;
        _inner = new GitHubCopilotAgent(new GitHubCopilotAgentOptions
        {
            AgentSlug        = "Squad",
            AgentId          = opts.AgentId,
            AgentName        = opts.AgentName,
            AgentDescription = opts.AgentDescription,
            SquadFolderPath  = opts.SquadFolderPath,
        });

        SessionsCreated.Add(1, new KeyValuePair<string, object?>("agent_id", _agentId));
    }

    public override async IAsyncEnumerable<string> RunAsync(
        string userMessage,
        AIAgentRunOptions? options = null,
        [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        using var activity = SquadActivitySource.StartActivity(
            "SquadAgent.Run",
            ActivityKind.Internal,
            tags: [new("agent_id", _agentId), new("message_length", userMessage.Length)]);

        RunsStartedCounter.Add(1, new KeyValuePair<string, object?>("agent_id", _agentId));
        var sw = Stopwatch.StartNew();

        bool success = false;
        try
        {
            await foreach (var chunk in _inner.RunAsync(userMessage, options, cancellationToken))
            {
                yield return chunk;
            }
            success = true;
        }
        finally
        {
            sw.Stop();
            RunDurationMs.Record(sw.Elapsed.TotalMilliseconds,
                new KeyValuePair<string, object?>("agent_id", _agentId),
                new KeyValuePair<string, object?>("success", success));
            RunsCompletedCounter.Add(1,
                new KeyValuePair<string, object?>("agent_id", _agentId),
                new KeyValuePair<string, object?>("success", success));
            activity?.SetTag("success", success);
        }
    }

    public async ValueTask DisposeAsync()
    {
        if (_inner is IAsyncDisposable d) await d.DisposeAsync();
    }
}
