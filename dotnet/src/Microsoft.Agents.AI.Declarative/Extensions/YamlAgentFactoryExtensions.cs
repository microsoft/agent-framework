// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Extension methods for <see cref="PromptAgentFactory"/> to support YAML based agent definitions.
/// </summary>
public static class YamlAgentFactoryExtensions
{
    /// <summary>
    /// Create a <see cref="AIAgent"/> from the given agent YAML.
    /// </summary>
    /// <param name="agentFactory"><see cref="PromptAgentFactory"/> which will be used to create the agent.</param>
    /// <param name="agentYaml">Text string containing the YAML representation of an <see cref="AIAgent" />.</param>
    /// <param name="cancellationToken">Optional cancellation token</param>
    [RequiresDynamicCode("Calls YamlDotNet.Serialization.DeserializerBuilder.DeserializerBuilder()")]
    public static Task<AIAgent> CreateFromYamlAsync(this PromptAgentFactory agentFactory, string agentYaml, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentFactory);
        Throw.IfNullOrEmpty(agentYaml);

        var agentDefinition = AgentBotElementYaml.FromYaml(agentYaml);

        return agentFactory.CreateAsync(
            agentDefinition,
            cancellationToken);
    }
}
