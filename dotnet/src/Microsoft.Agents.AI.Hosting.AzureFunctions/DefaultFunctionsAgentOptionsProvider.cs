// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Provides access to agent-specific options for functions agents by name.
/// Returns default options (HTTP trigger enabled, MCP tool disabled) when no explicit options were configured.
/// </summary>
internal sealed class DefaultFunctionsAgentOptionsProvider(IReadOnlyDictionary<string, FunctionsAgentOptions> functionsAgentOptions)
    : IFunctionsAgentOptionsProvider
{
    private readonly IReadOnlyDictionary<string, FunctionsAgentOptions> _functionsAgentOptions =
        functionsAgentOptions ?? throw new ArgumentNullException(nameof(functionsAgentOptions));

    // Default options. HTTP trigger enabled, MCP tool disabled.
    private static readonly FunctionsAgentOptions s_defaultOptions = new()
    {
        HttpTrigger = { IsEnabled = true },
        McpToolTrigger = { IsEnabled = false }
    };

    /// <summary>
    /// Attempts to retrieve the options associated with the specified agent name.
    /// If not found, a default options instance (with HTTP trigger enabled) is returned.
    /// </summary>
    /// <param name="agentName">The name of the agent whose options are to be retrieved. Cannot be null or empty.</param>
    /// <param name="options">The options for the specified agent. Will never be null.</param>
    /// <returns>Always true. Returns configured options if present; otherwise default fallback options.</returns>
    public bool TryGet(string agentName, [NotNullWhen(true)] out FunctionsAgentOptions? options)
    {
        ArgumentException.ThrowIfNullOrEmpty(agentName);

        if (this._functionsAgentOptions.TryGetValue(agentName, out FunctionsAgentOptions? existing))
        {
            options = existing;
            return true;
        }

        // If not defined, return default options.
        options = s_defaultOptions;
        return true;
    }
}
