// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.Configuration;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Represents a factory for creating <see cref="AIAgent"/> instances.
/// </summary>
public abstract class PromptAgentFactory
{
    private const int DefaultMaximumExpressionLength = 10000;

    private readonly IConfiguration? _configuration;
    private readonly HashSet<string> _allowedConfigurationVariables;

    /// <summary>
    /// Initializes a new instance of the <see cref="PromptAgentFactory"/> class.
    /// </summary>
    /// <param name="engine">Optional <see cref="RecalcEngine"/>, if none is provided a default instance will be created.</param>
    /// <param name="configuration">Optional configuration used to resolve explicitly allowed environment variables referenced by the agent definition.</param>
    protected PromptAgentFactory(RecalcEngine? engine = null, IConfiguration? configuration = null)
        : this(engine, configuration, allowedConfigurationVariables: null)
    {
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="PromptAgentFactory"/> class.
    /// </summary>
    /// <param name="engine">Optional <see cref="RecalcEngine"/>, if none is provided a default instance will be created.</param>
    /// <param name="configuration">Optional configuration used to resolve explicitly allowed environment variables referenced by the agent definition.</param>
    /// <param name="allowedConfigurationVariables">Configuration keys that may be exposed to Power Fx when the agent definition references them through <c>Env</c>.</param>
    /// <param name="maximumExpressionLength">Optional maximum length for Power Fx expressions evaluated by the factory-created engine.</param>
    /// <param name="maximumCallDepth">Optional maximum nested call depth for Power Fx expressions evaluated by the factory-created engine.</param>
    protected PromptAgentFactory(
        RecalcEngine? engine,
        IConfiguration? configuration,
        IEnumerable<string>? allowedConfigurationVariables,
        int? maximumExpressionLength = null,
        int? maximumCallDepth = null)
    {
        this.Engine = engine ?? new RecalcEngine(CreateConfig(maximumExpressionLength, maximumCallDepth));
        this._configuration = configuration;
        this._allowedConfigurationVariables = new(allowedConfigurationVariables ?? [], StringComparer.OrdinalIgnoreCase);
    }

    private static PowerFxConfig CreateConfig(int? maximumExpressionLength, int? maximumCallDepth)
    {
        PowerFxConfig config = new(Features.PowerFxV1)
        {
            MaximumExpressionLength = maximumExpressionLength ?? DefaultMaximumExpressionLength,
        };

        if (maximumCallDepth is not null)
        {
            config.MaxCallDepth = maximumCallDepth.Value;
        }

        return config;
    }

    /// <summary>
    /// Gets the Power Fx recalculation engine used to evaluate expressions in agent definitions.
    /// This engine is configured with only explicitly allowed variables from the <see cref="IConfiguration"/> provided during construction.
    /// </summary>
    protected RecalcEngine Engine { get; }

    /// <summary>
    /// Adds allowed configuration values referenced through <c>Env</c> by the agent definition to the Power Fx engine.
    /// </summary>
    /// <param name="promptAgent">Definition of the agent to inspect.</param>
    protected void InitializeConfigurationVariables(GptComponentMetadata promptAgent)
    {
        if (this._configuration is null || this._allowedConfigurationVariables.Count == 0)
        {
            return;
        }

        foreach (string variableName in AgentBotElementYaml.GetReferencedEnvironmentVariableNames(promptAgent))
        {
            if (this._allowedConfigurationVariables.Contains(variableName))
            {
                this.Engine.UpdateVariable(variableName, this._configuration[variableName] ?? string.Empty);
            }
        }
    }

    [RequiresDynamicCode("Calls YamlDotNet.Serialization.DeserializerBuilder.DeserializerBuilder()")]
    internal GptComponentMetadata FromYaml(string text) =>
        AgentBotElementYaml.FromYaml(text, this._configuration, this._allowedConfigurationVariables);

    /// <summary>
    /// Create a <see cref="AIAgent"/> from the specified <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="promptAgent">Definition of the agent to create.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public async Task<AIAgent> CreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(promptAgent);

        var agent = await this.TryCreateAsync(promptAgent, cancellationToken).ConfigureAwait(false) ?? throw new NotSupportedException($"Agent type {promptAgent.Kind} is not supported.");
        Declarative.FeatureUsageMarker.MarkUsed();
        return agent;
    }

    /// <summary>
    /// Tries to create a <see cref="AIAgent"/> from the specified <see cref="GptComponentMetadata"/>.
    /// </summary>
    /// <param name="promptAgent">Definition of the agent to create.</param>
    /// <param name="cancellationToken">Optional cancellation token.</param>
    /// <return>The created <see cref="AIAgent"/>, if null the agent type is not supported.</return>
    public abstract Task<AIAgent?> TryCreateAsync(GptComponentMetadata promptAgent, CancellationToken cancellationToken = default);
}
