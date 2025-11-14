// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;

namespace Microsoft.Agents.AI.Hosting.AzureFunctions;

/// <summary>
/// Provides access to function trigger options for agents in the Azure Functions hosting environment.
/// </summary>
internal interface IFunctionsAgentOptionsProvider
{
    /// <summary>
    /// Attempts to get trigger options for the specified agent.
    /// </summary>
    /// <param name="agentName">The agent name.</param>
    /// <param name="options">The resulting options if found.</param>
    /// <returns>True if options exist; otherwise false.</returns>
    bool TryGet(string agentName, [NotNullWhen(true)] out FunctionsAgentOptions? options);
}
