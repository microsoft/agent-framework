// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Provides access to agent-specific options for functions agents by name.
/// Returns <see langword="false"/> when no explicit options have been configured for an agent,
/// which distinguishes standalone agents from those auto-registered by workflows.
/// </summary>
internal sealed class DefaultFunctionsAgentOptionsProvider(IReadOnlyDictionary<string, FunctionsAgentOptions> functionsAgentOptions)
    : IFunctionsAgentOptionsProvider
{
    private readonly IReadOnlyDictionary<string, FunctionsAgentOptions> _functionsAgentOptions =
        functionsAgentOptions ?? throw new ArgumentNullException(nameof(functionsAgentOptions));

    /// <summary>
    /// Attempts to retrieve the options associated with the specified agent name.
    /// Returns <see langword="false"/> when no options have been explicitly configured for the agent.
    /// </summary>
    /// <param name="agentName">The name of the agent whose options are to be retrieved. Cannot be null or empty.</param>
    /// <param name="options">
    /// When this method returns <see langword="true"/>, contains the options for the specified agent;
    /// otherwise, <see langword="null"/>.
    /// </param>
    /// <returns><see langword="true"/> if options were found for the agent; otherwise, <see langword="false"/>.</returns>
    public bool TryGet(string agentName, [NotNullWhen(true)] out FunctionsAgentOptions? options)
    {
        ArgumentException.ThrowIfNullOrEmpty(agentName);
        return this._functionsAgentOptions.TryGetValue(agentName, out options);
    }
}
