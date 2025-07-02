// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Microsoft.Agents;
using Microsoft.Extensions.AI.AzureAIAgentsPersistent;

namespace Microsoft.Extensions.AI;

/// <summary>
/// Provides extension methods for <see cref="PersistentAgentsClient"/>.
/// </summary>
public static class PersistentAgentsClientExtensions
{
    /// <summary>
    /// Creates an <see cref="IChatClient"/> for a <see cref="PersistentAgentsClient"/> client for interacting with a specific agent.
    /// </summary>
    /// <param name="client">The <see cref="PersistentAgentsClient"/> instance to be accessed as an <see cref="IChatClient"/>.</param>
    /// <param name="agentId">The unique identifier of the agent with which to interact.</param>
    /// <param name="threadId">
    /// An optional existing thread identifier for the chat session. This serves as a default, and may be overridden per call to
    /// <see cref="IChatClient.GetResponseAsync"/> or <see cref="IChatClient.GetStreamingResponseAsync"/> via the <see cref="ChatOptions.ConversationId"/>
    /// property. If not thread ID is provided via either mechanism, a new thread will be created for the request.
    /// </param>
    /// <returns>An <see cref="IChatClient"/> instance configured to interact with the specified agent and thread.</returns>
    public static IChatClient AsIChatClient(this PersistentAgentsClient client, string agentId, string? threadId = null) =>
        new PersistentAgentsChatClient(client, agentId, threadId);

    /// <summary>
    /// Creates a new server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="PersistentAgentsClient"/> with.</param>
    /// <returns>A <see cref="ChatClientAgent"/> for the created persistent agent.</returns>
    /// <param name="model"> The ID of the model to use. </param>
    /// <param name="name"> The name of the new agent. </param>
    /// <param name="description"> The description of the new agent. </param>
    /// <param name="instructions"> The system instructions for the new agent to use. </param>
    /// <param name="tools"> The collection of tools to enable for the new agent. </param>
    /// <param name="toolResources">
    /// A set of resources that are used by the agent's tools. The resources are specific to the type of tool. For example, the `code_interpreter`
    /// tool requires a list of file IDs, while the `file_search` tool requires a list of vector store IDs.
    /// </param>
    /// <param name="temperature">
    /// What sampling temperature to use, between 0 and 2. Higher values like 0.8 will make the output more random,
    /// while lower values like 0.2 will make it more focused and deterministic.
    /// </param>
    /// <param name="topP">
    /// An alternative to sampling with temperature, called nucleus sampling, where the model considers the results of the tokens with top_p probability mass.
    /// So 0.1 means only the tokens comprising the top 10% probability mass are considered.
    ///
    /// We generally recommend altering this or temperature but not both.
    /// </param>
    /// <param name="responseFormat"> The response format of the tool calls used by this agent. </param>
    /// <param name="metadata"> A set of up to 16 key/value pairs that can be attached to an object, used for storing additional information about that object in a structured format. Keys may be up to 64 characters in length and values may be up to 512 characters in length. </param>
    /// <param name="cancellationToken"> The cancellation token to use. </param>
    public static async Task<ChatClientAgent> CreateChatClientAgentAsync(
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
        // Create a server side agent to work with.
        var persistentAgentResponse = await persistentAgentsClient.Administration.CreateAgentAsync(
            model,
            name,
            description,
            instructions,
            tools,
            toolResources,
            temperature,
            topP,
            responseFormat,
            metadata,
            cancellationToken).ConfigureAwait(false);

        var persistentAgent = persistentAgentResponse.Value;

        // Get the chat client to use for the agent.
        using var chatClient = persistentAgentsClient.AsIChatClient(persistentAgent.Id);

        // Create the ChatClientAgent.
        return new(chatClient, new() { Id = persistentAgent.Id });
    }

    /// <summary>
    /// Retrieves an existing server side agent, wrapped as a <see cref="ChatClientAgent"/> using the provided <see cref="PersistentAgentsClient"/>.
    /// </summary>
    /// <param name="persistentAgentsClient">The <see cref="PersistentAgentsClient"/> to create the <see cref="PersistentAgentsClient"/> with.</param>
    /// <returns>A <see cref="ChatClientAgent"/> for the created persistent agent.</returns>
    /// <param name="agentId"> The ID of the server side agent to create a <see cref="ChatClientAgent"/> for.</param>
    /// <param name="chatOptions">Options that should apply to all runs of the agent.</param>
    public static ChatClientAgent GetChatClientAgent(this PersistentAgentsClient persistentAgentsClient, string agentId, ChatOptions? chatOptions = null)
    {
        // Get the chat client to use for the agent.
        using var chatClient = persistentAgentsClient.AsIChatClient(agentId);

        // Create the ChatClientAgent.
        return new(chatClient, new() { Id = agentId, ChatOptions = chatOptions });
    }
}
