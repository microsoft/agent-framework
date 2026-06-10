// Copyright (c) Microsoft. All rights reserved.
using Microsoft.Agents.AI;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Options;
using Squad.SquadWithDTS.Agents;

namespace Squad.SquadWithDTS.Infrastructure;

/// <summary>
/// Creates and configures MAF <see cref="AIAgent"/> instances from the
/// active LLM-provider configuration.
///
/// Supported providers (set via <c>SQUAD_AF_PROVIDER</c> / <c>appsettings.json</c>):
/// <list type="bullet">
///   <item><c>azure-openai</c></item>
///   <item><c>openai-compatible</c> (Ollama, Foundry Local, etc.)</item>
///   <item><c>none</c> — deterministic demo mode with no LLM calls</item>
/// </list>
/// </summary>
internal sealed class ProviderAgentFactory
{
    private readonly IConfiguration _config;
    private readonly SquadAgent _squad;

    public ProviderAgentFactory(IConfiguration config, SquadAgent squad)
    {
        _config = config;
        _squad  = squad;
        Summary = BuildSummary(config);
    }

    public ProviderSummary Summary { get; }

    /// <summary>
    /// Returns the Squad agent that is wired at construction time.
    /// </summary>
    public SquadAgent SquadAgent => _squad;

    /// <summary>
    /// Creates an ephemeral chat agent for the given <paramref name="name"/> / <paramref name="charter"/>.
    /// The caller is responsible for disposing the returned <see cref="IAsyncDisposable"/>.
    /// </summary>
    public (AIAgent Agent, IAsyncDisposable Scope) CreateAgent(string name, string charter)
    {
        var provider = Summary.Provider;

        if (!Summary.IsProviderBacked)
        {
            return (new DeterministicFallbackAgent(name), NoopDisposable.Instance);
        }

        AIAgent agent = provider switch
        {
            "azure-openai"       => CreateAzureOpenAIAgent(name, charter),
            "openai-compatible"  => CreateOpenAICompatibleAgent(name, charter),
            _ => throw new InvalidOperationException($"Unknown provider: {provider}")
        };

        return (agent, agent as IAsyncDisposable ?? NoopDisposable.Instance);
    }

    // ─── private helpers ─────────────────────────────────────────────────

    private AIAgent CreateAzureOpenAIAgent(string name, string charter)
    {
        // Use MAF's built-in Azure OpenAI agent type.
        // Replace with a real agent implementation for your environment.
        throw new NotImplementedException(
            "Azure OpenAI agent creation: bind Microsoft.Agents.AI.AzureOpenAI here.");
    }

    private AIAgent CreateOpenAICompatibleAgent(string name, string charter)
    {
        throw new NotImplementedException(
            "OpenAI-compatible agent creation: bind Microsoft.Agents.AI.OpenAI here.");
    }

    private static ProviderSummary BuildSummary(IConfiguration config)
    {
        var provider   = config["SQUAD_AF_PROVIDER"] ?? "none";
        var endpoint   = config["SQUAD_AF_ENDPOINT"];
        var deployment = config["SQUAD_AF_DEPLOYMENT"];
        var model      = config["SQUAD_AF_MODEL"];

        bool isBacked = provider is not ("none" or "");

        return new ProviderSummary(
            Provider: provider,
            Endpoint: endpoint ?? "(none)",
            Deployment: deployment ?? model ?? "(none)",
            IsProviderBacked: isBacked);
    }

    private sealed class NoopDisposable : IAsyncDisposable
    {
        public static readonly NoopDisposable Instance = new();
        public ValueTask DisposeAsync() => ValueTask.CompletedTask;
    }

    /// <summary>
    /// Deterministic no-LLM fallback used when no provider is configured.
    /// </summary>
    private sealed class DeterministicFallbackAgent(string name) : AIAgent
    {
        public override async IAsyncEnumerable<string> RunAsync(
            string userMessage,
            AIAgentRunOptions? options = null,
            [System.Runtime.CompilerServices.EnumeratorCancellation] CancellationToken cancellationToken = default)
        {
            await Task.Yield();
            yield return $"[{name}] DEMO FALLBACK — no LLM provider configured. " +
                         "Set SQUAD_AF_PROVIDER to 'azure-openai' or 'openai-compatible'.";
        }
    }
}

/// <summary>Read-only summary of the active LLM provider configuration.</summary>
internal sealed record ProviderSummary(
    string Provider,
    string Endpoint,
    string Deployment,
    bool   IsProviderBacked);
