// Copyright (c) Microsoft. All rights reserved.

using Azure;
using Azure.AI.Agents.Persistent;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Extensions.AI.AzureAIAgentsPersistent;

/// <summary>
/// Provides extension methods for working with <see cref="Response{PersistentAgent}"/>.
/// </summary>
public static class PersistentAgentResponseExtensions
{
    /// <summary>
    /// Converts a response containing a persistent agent into a runnable agent instance.
    /// </summary>
    /// <param name="persistentAgentResponse">The response containing the persistent agent to be converted. Cannot be <see langword="null"/>.</param>
    /// <param name="persistentAgentsClient">The client used to interact with persistent agents. Cannot be <see langword="null"/>.</param>
    /// <returns>A <see cref="FoundryAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static FoundryAgent AsRunnableAgent(this Response<PersistentAgent> persistentAgentResponse, PersistentAgentsClient persistentAgentsClient)
    {
        Throw.IfNull(persistentAgentResponse);
        Throw.IfNull(persistentAgentsClient);

        return new FoundryAgent(persistentAgentsClient, persistentAgentResponse.Value);
    }
}
