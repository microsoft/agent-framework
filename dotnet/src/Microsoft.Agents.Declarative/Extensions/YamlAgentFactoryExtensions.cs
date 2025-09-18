// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI.Agents;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Declarative;

/// <summary>
/// Extension methods for <see cref="AgentFactory"/> to support YAML based agent definitions.
/// </summary>
public static class YamlAgentFactoryExtensions
{
    /// <summary>
    /// Create a <see cref="AIAgent"/> from the given YAML text.
    /// </summary>
    /// <param name="agentFactory"><see cref="AgentFactory"/> which will be used to create the agent.</param>
    /// <param name="text">Text string containing the YAML representation of an <see cref="AIAgent" />.</param>
    /// <param name="options"><see cref="AgentCreationOptions"/> instance.</param>
    /// <param name="cancellationToken">Optional cancellation token</param>
    [RequiresDynamicCode("Calls YamlDotNet.Serialization.DeserializerBuilder.DeserializerBuilder()")]
    public static async Task<AIAgent?> CreateFromYamlAsync(this AgentFactory agentFactory, string text, AgentCreationOptions? options = null, CancellationToken cancellationToken = default)
    {
        Throw.IfNull(agentFactory);
        Throw.IfNullOrEmpty(text);

        var agentDefinition = AgentBotElementYaml.FromYaml(text);

        return await agentFactory.CreateAsync(
            agentDefinition,
            options ?? new(),
            cancellationToken).ConfigureAwait(false);
    }
}
