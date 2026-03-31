// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Azure.AI.Projects.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.DiagnosticIds;
using OpenAI.Responses;

#pragma warning disable OPENAI001

namespace Microsoft.Agents.AI.AzureAI;

/// <summary>
/// Provides factory methods for creating <see cref="AITool"/> instances from Microsoft Foundry and OpenAI response tools.
/// </summary>
/// <remarks>
/// <para>
/// This class wraps <see cref="AgentTool"/> (Azure.AI.Projects.OpenAI) and <see cref="ResponseTool"/> (OpenAI SDK) factory methods,
/// returning <see cref="AITool"/> directly — eliminating the need for manual casting and <c>.AsAITool()</c> calls.
/// </para>
/// <para>
/// Instead of writing:
/// <c>((ResponseTool)AgentTool.CreateOpenApiTool(definition)).AsAITool()</c>
/// You can write:
/// <c>FoundryAITool.CreateOpenApiTool(definition)</c>
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AIOpenAIResponses)]
public static class FoundryAITool
{
    /// <summary>
    /// Converts an existing <see cref="ResponseTool"/> into an <see cref="AITool"/>.
    /// </summary>
    /// <param name="responseTool">The response tool to convert.</param>
    /// <returns>An <see cref="AITool"/> wrapping the provided response tool.</returns>
    public static AITool FromResponseTool(ResponseTool responseTool) => responseTool.AsAITool();

    // --- Azure.AI.Projects.OpenAI AgentTool factories ---

    /// <summary>
    /// Creates an <see cref="AITool"/> for OpenAPI tool invocations.
    /// </summary>
    /// <param name="definition">The OpenAPI function definition specifying the API endpoint, schema, and authentication.</param>
    /// <returns>An <see cref="AITool"/> that calls the specified OpenAPI endpoint.</returns>
    public static AITool CreateOpenApiTool(OpenApiFunctionDefinition definition)
        => ((ResponseTool)AgentTool.CreateOpenApiTool(definition)).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for Bing Grounding search.
    /// </summary>
    /// <param name="options">The Bing Grounding search configuration options.</param>
    /// <returns>An <see cref="AITool"/> for Bing Grounding search.</returns>
    public static AITool CreateBingGroundingTool(BingGroundingSearchToolOptions options)
        => ((ResponseTool)AgentTool.CreateBingGroundingTool(options)).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for Bing Custom Search.
    /// </summary>
    /// <param name="parameters">The Bing Custom Search configuration parameters.</param>
    /// <returns>An <see cref="AITool"/> for Bing Custom Search.</returns>
    public static AITool CreateBingCustomSearchTool(BingCustomSearchToolOptions parameters)
        => ((ResponseTool)AgentTool.CreateBingCustomSearchTool(parameters)).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for Microsoft Fabric data agent.
    /// </summary>
    /// <param name="options">The Fabric data agent configuration options.</param>
    /// <returns>An <see cref="AITool"/> for Microsoft Fabric.</returns>
    public static AITool CreateMicrosoftFabricTool(FabricDataAgentToolOptions options)
        => ((ResponseTool)AgentTool.CreateMicrosoftFabricTool(options)).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for SharePoint grounding.
    /// </summary>
    /// <param name="options">The SharePoint grounding configuration options.</param>
    /// <returns>An <see cref="AITool"/> for SharePoint grounding.</returns>
    public static AITool CreateSharepointTool(SharePointGroundingToolOptions options)
        => ((ResponseTool)AgentTool.CreateSharepointTool(options)).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for Azure AI Search.
    /// </summary>
    /// <param name="options">Optional Azure AI Search configuration options.</param>
    /// <returns>An <see cref="AITool"/> for Azure AI Search.</returns>
    public static AITool CreateAzureAISearchTool(AzureAISearchToolOptions? options = null)
        => ((ResponseTool)AgentTool.CreateAzureAISearchTool(options)).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for browser automation.
    /// </summary>
    /// <param name="parameters">The browser automation configuration parameters.</param>
    /// <returns>An <see cref="AITool"/> for browser automation.</returns>
    public static AITool CreateBrowserAutomationTool(BrowserAutomationToolOptions parameters)
        => ((ResponseTool)AgentTool.CreateBrowserAutomationTool(parameters)).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for structured output capture.
    /// </summary>
    /// <param name="outputs">The structured output definition.</param>
    /// <returns>An <see cref="AITool"/> for structured output capture.</returns>
    public static AITool CreateStructuredOutputsTool(StructuredOutputDefinition outputs)
        => ((ResponseTool)AgentTool.CreateStructuredOutputsTool(outputs)).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for Agent-to-Agent (A2A) communication.
    /// </summary>
    /// <param name="baseUri">The base URI for the A2A agent.</param>
    /// <param name="agentCardPath">Optional path to the agent card.</param>
    /// <returns>An <see cref="AITool"/> for A2A communication.</returns>
    public static AITool CreateA2ATool(Uri baseUri, string? agentCardPath = null)
        => AgentTool.CreateA2ATool(baseUri, agentCardPath).AsAITool();

    // --- OpenAI SDK ResponseTool factories ---

    /// <summary>
    /// Creates an <see cref="AITool"/> for computer use (screen interaction).
    /// </summary>
    /// <param name="environment">The computer tool environment type.</param>
    /// <param name="displayWidth">The display width in pixels.</param>
    /// <param name="displayHeight">The display height in pixels.</param>
    /// <returns>An <see cref="AITool"/> for computer use.</returns>
    [Experimental("OPENAICUA001")]
    public static AITool CreateComputerTool(ComputerToolEnvironment environment, int displayWidth, int displayHeight)
        => ResponseTool.CreateComputerTool(environment, displayWidth, displayHeight).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for function tool invocations.
    /// </summary>
    /// <param name="functionName">The name of the function.</param>
    /// <param name="functionParameters">The function parameters schema as JSON.</param>
    /// <param name="strictModeEnabled">Whether strict mode is enabled for parameter validation.</param>
    /// <param name="functionDescription">Optional description of the function.</param>
    /// <returns>An <see cref="AITool"/> for function invocations.</returns>
    public static AITool CreateFunctionTool(string functionName, BinaryData functionParameters, bool? strictModeEnabled, string? functionDescription = null)
        => ResponseTool.CreateFunctionTool(functionName, functionParameters, strictModeEnabled, functionDescription).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for file search over vector stores.
    /// </summary>
    /// <param name="vectorStoreIds">The IDs of vector stores to search.</param>
    /// <param name="maxResultCount">Optional maximum number of results to return.</param>
    /// <param name="rankingOptions">Optional ranking options for search results.</param>
    /// <param name="filters">Optional filters for search results.</param>
    /// <returns>An <see cref="AITool"/> for file search.</returns>
    public static AITool CreateFileSearchTool(IEnumerable<string> vectorStoreIds, int? maxResultCount = null, FileSearchToolRankingOptions? rankingOptions = null, BinaryData? filters = null)
        => ResponseTool.CreateFileSearchTool(vectorStoreIds, maxResultCount, rankingOptions, filters).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for web search.
    /// </summary>
    /// <param name="userLocation">Optional user location for search context.</param>
    /// <param name="searchContextSize">Optional search context size.</param>
    /// <param name="filters">Optional search filters.</param>
    /// <returns>An <see cref="AITool"/> for web search.</returns>
    public static AITool CreateWebSearchTool(WebSearchToolLocation? userLocation = null, WebSearchToolContextSize? searchContextSize = null, WebSearchToolFilters? filters = null)
        => ResponseTool.CreateWebSearchTool(userLocation, searchContextSize, filters).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for MCP (Model Context Protocol) server tools.
    /// </summary>
    /// <param name="serverLabel">The label for the MCP server.</param>
    /// <param name="serverUri">The URI of the MCP server.</param>
    /// <param name="authorizationToken">Optional authorization token.</param>
    /// <param name="serverDescription">Optional server description.</param>
    /// <param name="headers">Optional custom headers.</param>
    /// <param name="allowedTools">Optional filter for allowed tools.</param>
    /// <param name="toolCallApprovalPolicy">Optional tool call approval policy.</param>
    /// <returns>An <see cref="AITool"/> for MCP server tools.</returns>
    public static AITool CreateMcpTool(string serverLabel, Uri serverUri, string? authorizationToken = null, string? serverDescription = null, IDictionary<string, string>? headers = null, McpToolFilter? allowedTools = null, McpToolCallApprovalPolicy? toolCallApprovalPolicy = null)
        => ResponseTool.CreateMcpTool(serverLabel, serverUri, authorizationToken, serverDescription, headers, allowedTools, toolCallApprovalPolicy).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for MCP (Model Context Protocol) server tools using a connector ID.
    /// </summary>
    /// <param name="serverLabel">The label for the MCP server.</param>
    /// <param name="connectorId">The connector ID for the MCP server.</param>
    /// <param name="authorizationToken">Optional authorization token.</param>
    /// <param name="serverDescription">Optional server description.</param>
    /// <param name="headers">Optional custom headers.</param>
    /// <param name="allowedTools">Optional filter for allowed tools.</param>
    /// <param name="toolCallApprovalPolicy">Optional tool call approval policy.</param>
    /// <returns>An <see cref="AITool"/> for MCP server tools.</returns>
    public static AITool CreateMcpTool(string serverLabel, McpToolConnectorId connectorId, string? authorizationToken = null, string? serverDescription = null, IDictionary<string, string>? headers = null, McpToolFilter? allowedTools = null, McpToolCallApprovalPolicy? toolCallApprovalPolicy = null)
        => ResponseTool.CreateMcpTool(serverLabel, connectorId, authorizationToken, serverDescription, headers, allowedTools, toolCallApprovalPolicy).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for code interpreter.
    /// </summary>
    /// <param name="container">The container configuration for the code interpreter.</param>
    /// <returns>An <see cref="AITool"/> for code interpreter.</returns>
    public static AITool CreateCodeInterpreterTool(CodeInterpreterToolContainer container)
        => ResponseTool.CreateCodeInterpreterTool(container).AsAITool();

    /// <summary>
    /// Creates an <see cref="AITool"/> for image generation.
    /// </summary>
    /// <param name="model">The model to use for image generation.</param>
    /// <param name="quality">Optional image quality setting.</param>
    /// <param name="size">Optional image size setting.</param>
    /// <param name="outputFileFormat">Optional output file format.</param>
    /// <param name="outputCompressionFactor">Optional output compression factor.</param>
    /// <param name="moderationLevel">Optional moderation level.</param>
    /// <param name="background">Optional background setting.</param>
    /// <param name="inputFidelity">Optional input fidelity setting.</param>
    /// <param name="inputImageMask">Optional input image mask.</param>
    /// <param name="partialImageCount">Optional partial image count.</param>
    /// <returns>An <see cref="AITool"/> for image generation.</returns>
    public static AITool CreateImageGenerationTool(string model, ImageGenerationToolQuality? quality = null, ImageGenerationToolSize? size = null, ImageGenerationToolOutputFileFormat? outputFileFormat = null, int? outputCompressionFactor = null, ImageGenerationToolModerationLevel? moderationLevel = null, ImageGenerationToolBackground? background = null, ImageGenerationToolInputFidelity? inputFidelity = null, ImageGenerationToolInputImageMask? inputImageMask = null, int? partialImageCount = null)
        => ResponseTool.CreateImageGenerationTool(model, quality, size, outputFileFormat, outputCompressionFactor, moderationLevel, background, inputFidelity, inputImageMask, partialImageCount).AsAITool();
}
