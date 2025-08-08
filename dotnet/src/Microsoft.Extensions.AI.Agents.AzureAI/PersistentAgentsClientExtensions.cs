// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Azure.AI.Agents.Persistent;

/// <summary>
/// Provides extension methods for <see cref="PersistentAgentsClient"/>.
/// </summary>
public static class PersistentAgentsClientExtensions
{
    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="ChatClientAgent"/> with.</param>
    /// <returns>A <see cref="ChatClientAgent"/> for the persistent agent.</returns>
    /// <param name="agentId"> The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="chatOptions">Options that should apply to all runs of the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the persistent agent.</returns>
    public static async Task<ChatClientAgent> GetAIAgentAsync(
        this PersistentAgentsClient persistentAgentsClient,
        string agentId,
        ChatOptions? chatOptions = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        if (string.IsNullOrWhiteSpace(agentId))
        {
            throw new ArgumentException($"{nameof(agentId)} should not be null or whitespace.", nameof(agentId));
        }

        var persistentAgentResponse = await persistentAgentsClient.Administration.GetAgentAsync(agentId, cancellationToken).ConfigureAwait(false);
        return persistentAgentResponse.AsAIAgent(persistentAgentsClient, chatOptions);
    }

    /// <summary>
    /// Creates a new server side agent using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the agent with.</param>
    /// <param name="model">The model to be used by the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="tools">The tools to be used by the agent.</param>
    /// <param name="toolResources">The resources for the tools.</param>
    /// <param name="temperature">The temperature setting for the agent.</param>
    /// <param name="topP">The top-p setting for the agent.</param>
    /// <param name="responseFormat">The response format for the agent.</param>
    /// <param name="metadata">The metadata for the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
        this PersistentAgentsClient persistentAgentsClient,
        string model,
        string? name = null,
        string? description = null,
        string? instructions = null,
        IEnumerable<ToolDefinition>? tools = null,
        ToolResources? toolResources = null,
        float? temperature = null,
        float? topP = null,
        BinaryData? responseFormat = null,
        IReadOnlyDictionary<string, string>? metadata = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        var createPersistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
            model,
            name,
            instructions,
            tools: tools,
            toolResources: toolResources,
            temperature: temperature,
            topP: topP,
            responseFormat: responseFormat,
            metadata: metadata,
            cancellationToken: cancellationToken).ConfigureAwait(false);

        // Get a local proxy for the agent to work with.
        return await persistentAgentsClient.GetAIAgentAsync(createPersistentAgentResponse.Value.Id, cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    /// <summary>
    /// Creates a new server side agent using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the agent with.</param>
    /// <param name="model">The model to be used by the agent.</param>
    /// <param name="tools">The AI tools to be used by the agent.</param>
    /// <param name="name">The name of the agent.</param>
    /// <param name="description">The description of the agent.</param>
    /// <param name="instructions">The instructions for the agent.</param>
    /// <param name="temperature">The temperature setting for the agent.</param>
    /// <param name="topP">The top-p setting for the agent.</param>
    /// <param name="responseFormat">The response format for the agent.</param>
    /// <param name="metadata">The metadata for the agent.</param>
    /// <param name="cancellationToken">The <see cref="CancellationToken"/> to monitor for cancellation requests. The default is <see cref="CancellationToken.None"/>.</param>
    /// <returns>A <see cref="ChatClientAgent"/> instance that can be used to perform operations on the newly created agent.</returns>
    public static async Task<ChatClientAgent> CreateAIAgentAsync(
         this PersistentAgentsClient persistentAgentsClient,
        string model,
        IEnumerable<AITool>? tools,
        string? name = null,
        string? description = null,
        string? instructions = null,
        float? temperature = null,
        float? topP = null,
        BinaryData? responseFormat = null,
        IReadOnlyDictionary<string, string>? metadata = null,
        CancellationToken cancellationToken = default)
    {
        if (persistentAgentsClient is null)
        {
            throw new ArgumentNullException(nameof(persistentAgentsClient));
        }

        var (toolsDefinitions, toolResources) = GetToolsAndResources(tools);

        var createPersistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
             model,
             name,
             instructions,
             temperature: temperature,
             topP: topP,
             responseFormat: responseFormat,
             metadata: metadata,
             cancellationToken: cancellationToken).ConfigureAwait(false);

        // Get a local proxy for the agent to work with.
        return await persistentAgentsClient.GetAIAgentAsync(
            createPersistentAgentResponse.Value.Id,
            chatOptions: new() { Tools = tools?.ToList() },
            cancellationToken: cancellationToken).ConfigureAwait(false);
    }

    private static (List<ToolDefinition>? Tools, ToolResources? ToolResources) GetToolsAndResources(IEnumerable<AITool>? tools)
    {
        if (tools is null)
        {
            return (null, null);
        }

        List<ToolDefinition> toolDefinitions = [];
        ToolResources? toolResources = null;

        // Now add the tools from ChatOptions.Tools.
        foreach (AITool tool in tools)
        {
            switch (tool)
            {
                case AIFunction aiFunction:
                    toolDefinitions.Add(new FunctionToolDefinition(
                        aiFunction.Name,
                        aiFunction.Description,
                        BinaryData.FromBytes(JsonSerializer.SerializeToUtf8Bytes(aiFunction.JsonSchema, NewPersistentAgentsChatClient.AgentsChatClientJsonContext.Default.JsonElement))));
                    break;

                case NewHostedCodeInterpreterTool codeTool:
                    toolDefinitions.Add(new CodeInterpreterToolDefinition());

                    if (codeTool.Inputs is { Count: > 0 })
                    {
                        foreach (var input in codeTool.Inputs)
                        {
                            switch (input)
                            {
                                case HostedFileContent hostedFile:
                                    // If the input is a HostedFileContent, we can use its ID directly.
                                    (toolResources ??= new() { CodeInterpreter = new() }).CodeInterpreter.FileIds.Add(hostedFile.FileId);
                                    break;
                            }
                        }
                    }
                    break;

                case NewHostedFileSearchTool fileSearchTool:
                    toolDefinitions.Add(new FileSearchToolDefinition());

                    if (fileSearchTool.Inputs is { Count: > 0 })
                    {
                        foreach (var input in fileSearchTool.Inputs)
                        {
                            switch (input)
                            {
                                case HostedVectorStoreContent hostedVectorStore:
                                    // If the input is a HostedFileContent, we can use its ID directly.
                                    (toolResources ??= new() { FileSearch = new() }).FileSearch.VectorStoreIds.Add(hostedVectorStore.VectorStoreId);
                                    break;
                            }
                        }
                    }

                    break;

                case HostedWebSearchTool webSearch when webSearch.AdditionalProperties?.TryGetValue("connectionId", out object? connectionId) is true:
                    toolDefinitions.Add(new BingGroundingToolDefinition(new BingGroundingSearchToolParameters([new BingGroundingSearchConfiguration(connectionId!.ToString())])));
                    break;
            }
        }

        return (toolDefinitions.Count == 0 ? null : toolDefinitions, toolResources);
    }
}
