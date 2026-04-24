// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Foundry.Hosting;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

#pragma warning disable OPENAI001
#pragma warning disable AAIP001 // AgentToolboxes is experimental in Azure.AI.Projects.Agents

namespace Azure.AI.Projects;

/// <summary>
/// Provides extension methods on <see cref="AIProjectClient"/> for fetching
/// Foundry toolbox definitions as server-side tools.
/// </summary>
/// <remarks>
/// These extensions mirror Python's <c>FoundryChatClient.get_toolbox()</c> pattern,
/// allowing a single call on the project client to retrieve tools ready for use
/// with <c>AsAIAgent(model, instructions, tools: ...)</c>.
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public static class AIProjectClientToolboxExtensions
{
    /// <summary>
    /// Fetches a toolbox from the Foundry project and returns its tools as <see cref="AITool"/> instances
    /// ready for use as server-side tools in the Responses API.
    /// </summary>
    /// <param name="projectClient">The <see cref="AIProjectClient"/> to use. Cannot be <see langword="null"/>.</param>
    /// <param name="name">The name of the toolbox to fetch.</param>
    /// <param name="version">
    /// The specific toolbox version to fetch. When <see langword="null"/>, the toolbox's
    /// default version is resolved automatically.
    /// </param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A read-only list of <see cref="AITool"/> instances from the toolbox.</returns>
    /// <exception cref="System.ArgumentNullException">
    /// Thrown when <paramref name="projectClient"/> or <paramref name="name"/> is <see langword="null"/>.
    /// </exception>
    public static async Task<IReadOnlyList<AITool>> GetToolboxToolsAsync(
        this AIProjectClient projectClient,
        string name,
        string? version = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(projectClient);
        Throw.IfNullOrWhitespace(name);

        var toolboxClient = projectClient.AgentAdministrationClient.GetAgentToolboxes();
        var toolboxVersion = await FoundryToolbox.GetToolboxVersionCoreAsync(toolboxClient, name, version, cancellationToken).ConfigureAwait(false);
        return toolboxVersion.ToAITools();
    }
}
