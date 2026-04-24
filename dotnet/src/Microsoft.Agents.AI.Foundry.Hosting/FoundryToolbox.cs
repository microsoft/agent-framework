// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Linq;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

#pragma warning disable OPENAI001
#pragma warning disable AAIP001 // AgentToolboxes is experimental in Azure.AI.Projects.Agents
#pragma warning disable IL2026 // ModelReaderWriter.Read<ResponseTool> uses reflection; suppressed for Azure SDK model types.
#pragma warning disable IL3050 // ModelReaderWriter.Read<ResponseTool> requires dynamic code; suppressed for Azure SDK model types.

namespace Microsoft.Agents.AI.Foundry.Hosting;

/// <summary>
/// Provides methods for fetching Foundry toolbox definitions and converting their tools
/// to <see cref="AITool"/> instances for use as server-side tools in the Responses API.
/// </summary>
/// <remarks>
/// <para>
/// When tools from a toolbox are passed to a Foundry agent (e.g. via <c>AsAIAgent(model, instructions, tools: ...)</c>),
/// they are sent as server-side tool definitions in the Responses API request. The Foundry platform
/// handles tool execution — the agent process does not invoke tools locally.
/// </para>
/// <para>
/// This is the dotnet equivalent of Python's <c>FoundryChatClient.get_toolbox()</c> pattern.
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public static class FoundryToolbox
{
    /// <summary>
    /// Fetches a toolbox version from the Foundry project and returns the raw SDK <see cref="ToolboxVersion"/>.
    /// </summary>
    /// <param name="projectEndpoint">The Foundry project endpoint URI.</param>
    /// <param name="credential">The authentication credential used to access the Foundry project.</param>
    /// <param name="name">The name of the toolbox to fetch.</param>
    /// <param name="version">
    /// The specific toolbox version to fetch. When <see langword="null"/>, the toolbox's
    /// default version is resolved automatically (requires an additional API call).
    /// </param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>The <see cref="ToolboxVersion"/> containing tool definitions.</returns>
    /// <exception cref="ArgumentNullException">
    /// Thrown when <paramref name="projectEndpoint"/>, <paramref name="credential"/>, or <paramref name="name"/> is <see langword="null"/>.
    /// </exception>
    /// <exception cref="ClientResultException">Thrown when the Foundry project API returns an error.</exception>
    public static async Task<ToolboxVersion> GetToolboxVersionAsync(
        Uri projectEndpoint,
        AuthenticationTokenProvider credential,
        string name,
        string? version = null,
        CancellationToken cancellationToken = default)
    {
        Throw.IfNull(projectEndpoint);
        Throw.IfNull(credential);
        Throw.IfNullOrWhitespace(name);

        var toolboxClient = CreateToolboxClient(projectEndpoint, credential);
        return await GetToolboxVersionCoreAsync(toolboxClient, name, version, cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Fetches a toolbox from the Foundry project and returns its tools as <see cref="AITool"/> instances
    /// ready for use as server-side tools in the Responses API.
    /// </summary>
    /// <param name="projectEndpoint">The Foundry project endpoint URI.</param>
    /// <param name="credential">The authentication credential used to access the Foundry project.</param>
    /// <param name="name">The name of the toolbox to fetch.</param>
    /// <param name="version">
    /// The specific toolbox version to fetch. When <see langword="null"/>, the toolbox's
    /// default version is resolved automatically.
    /// </param>
    /// <param name="cancellationToken">A token to monitor for cancellation requests.</param>
    /// <returns>A read-only list of <see cref="AITool"/> instances from the toolbox.</returns>
    /// <exception cref="ArgumentNullException">
    /// Thrown when <paramref name="projectEndpoint"/>, <paramref name="credential"/>, or <paramref name="name"/> is <see langword="null"/>.
    /// </exception>
    /// <exception cref="ClientResultException">Thrown when the Foundry project API returns an error.</exception>
    public static async Task<IReadOnlyList<AITool>> GetToolsAsync(
        Uri projectEndpoint,
        AuthenticationTokenProvider credential,
        string name,
        string? version = null,
        CancellationToken cancellationToken = default)
    {
        var toolboxVersion = await GetToolboxVersionAsync(projectEndpoint, credential, name, version, cancellationToken).ConfigureAwait(false);
        return toolboxVersion.ToAITools();
    }

    /// <summary>
    /// Converts the tools in a <see cref="ToolboxVersion"/> to <see cref="AITool"/> instances
    /// suitable for use as server-side tools in the Responses API.
    /// </summary>
    /// <param name="toolboxVersion">The toolbox version whose tools to convert.</param>
    /// <returns>A read-only list of <see cref="AITool"/> instances.</returns>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="toolboxVersion"/> is <see langword="null"/>.</exception>
    /// <remarks>
    /// <para>
    /// Each <see cref="ProjectsAgentTool"/> in the toolbox is cast to <see cref="ResponseTool"/>
    /// and converted via <c>AsAITool()</c>. Non-function hosted tools (MCP, web_search,
    /// code_interpreter, etc.) are included as server-side tool definitions — the Foundry
    /// platform handles their execution.
    /// </para>
    /// <para>
    /// Non-function tools are sanitized to remove decoration fields (<c>name</c>, <c>description</c>)
    /// that the toolbox API returns but the Responses API rejects.
    /// </para>
    /// </remarks>
    public static IReadOnlyList<AITool> ToAITools(this ToolboxVersion toolboxVersion)
    {
        Throw.IfNull(toolboxVersion);

        if (toolboxVersion.Tools?.Any() != true)
        {
            return [];
        }

        return toolboxVersion.Tools
            .Select(SanitizeAndConvert)
            .ToList();
    }

    #region Internal helpers (visible to unit tests via InternalsVisibleTo)

    /// <summary>
    /// Sanitizes a <see cref="ProjectsAgentTool"/> by removing decoration fields that the
    /// toolbox API returns but the Responses API rejects, then converts to <see cref="AITool"/>.
    /// </summary>
    /// <remarks>
    /// The Azure AI Projects toolbox API may return <c>name</c> and <c>description</c> on
    /// hosted tool objects (MCP, code_interpreter, file_search, etc.). The Responses API
    /// rejects at least <c>name</c> with "Unknown parameter: 'tools[0].name'". We strip
    /// these decoration fields for non-function tools. Function tools keep them since
    /// <c>name</c> and <c>description</c> are expected parts of the function schema.
    /// </remarks>
    internal static AITool SanitizeAndConvert(ProjectsAgentTool tool)
    {
        var toolJson = ModelReaderWriter.Write(tool, new ModelReaderWriterOptions("J"));
        var node = JsonNode.Parse(toolJson.ToString());
        if (node is not JsonObject obj)
        {
            return ((ResponseTool)tool).AsAITool();
        }

        var toolType = obj["type"]?.GetValue<string>();

        // Function tools need name/description — don't strip
        if (toolType is "function" or "custom")
        {
            return ((ResponseTool)tool).AsAITool();
        }

        // Strip decoration fields that the Responses API rejects
        bool modified = false;
        modified |= obj.Remove("name");
        modified |= obj.Remove("description");

        if (!modified)
        {
            return ((ResponseTool)tool).AsAITool();
        }

        var sanitizedJson = obj.ToJsonString();
        var sanitizedTool = ModelReaderWriter.Read<ResponseTool>(BinaryData.FromString(sanitizedJson))!;
        return sanitizedTool.AsAITool();
    }

    internal static async Task<ToolboxVersion> GetToolboxVersionAsync(
        Uri projectEndpoint,
        AuthenticationTokenProvider credential,
        string name,
        string? version,
        AgentAdministrationClientOptions? clientOptions,
        CancellationToken cancellationToken)
    {
        Throw.IfNull(projectEndpoint);
        Throw.IfNull(credential);
        Throw.IfNullOrWhitespace(name);

        var toolboxClient = CreateToolboxClient(projectEndpoint, credential, clientOptions);
        return await GetToolboxVersionCoreAsync(toolboxClient, name, version, cancellationToken).ConfigureAwait(false);
    }

    internal static AgentToolboxes CreateToolboxClient(
        Uri projectEndpoint,
        AuthenticationTokenProvider credential,
        AgentAdministrationClientOptions? clientOptions = null)
    {
        clientOptions ??= new AgentAdministrationClientOptions();
        var adminClient = new AgentAdministrationClient(projectEndpoint, credential, clientOptions);
        return adminClient.GetAgentToolboxes();
    }

    internal static async Task<ToolboxVersion> GetToolboxVersionCoreAsync(
        AgentToolboxes toolboxClient,
        string name,
        string? version,
        CancellationToken cancellationToken)
    {
        if (version is null)
        {
            var record = await toolboxClient.GetToolboxAsync(name, cancellationToken).ConfigureAwait(false);
            version = record.Value.DefaultVersion
                ?? throw new InvalidOperationException($"Toolbox '{name}' does not have a default version. Specify an explicit version.");
        }

        var result = await toolboxClient.GetToolboxVersionAsync(name, version, cancellationToken).ConfigureAwait(false);
        return result.Value;
    }

    #endregion
}
