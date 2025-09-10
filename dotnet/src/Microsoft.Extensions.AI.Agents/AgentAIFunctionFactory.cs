// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.Shared.Diagnostics;
using static Microsoft.Extensions.AI.Agents.OpenTelemetryConsts.GenAI;

namespace Microsoft.Extensions.AI.Agents;

/// <summary>
/// Provides factory methods for creating implementations of <see cref="AIFunction"/> backed by an <see cref="AIAgent" />.
/// </summary>
public static class AgentAIFunctionFactory
{
    /// <summary>
    /// Creates a <see cref="AIFunction"/> that will invoke the provided Agent.
    /// </summary>
    /// <param name="agent">The <see cref="Agent" /> to be represented via the created <see cref="AIFunction"/>.</param>
    /// <param name="options">Metadata to use to override defaults inferred from <paramref name="agent"/>.</param>
    /// <returns>The created <see cref="AIFunction"/> for invoking the <see cref="AIAgent"/>.</returns>
    public static AIFunction CreateFromAgent(
        AIAgent agent,
        AIFunctionFactoryOptions? options = null)
    {
        Throw.IfNull(agent);

        async Task<string> RunAgentAsync(string query, CancellationToken cancellationToken)
        {
            var response = await agent.RunAsync(query, cancellationToken: cancellationToken).ConfigureAwait(false);
            return response.Text;
        }

        return AIFunctionFactory.Create(RunAgentAsync, options ?? new()
        {
            Name = agent.Name,
            Description = agent.Description,
        });
    }
}
