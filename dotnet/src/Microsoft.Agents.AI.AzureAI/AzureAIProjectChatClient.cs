// Copyright (c) Microsoft. All rights reserved.

using System.Runtime.CompilerServices;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

namespace Microsoft.Agents.AI.AzureAI;

/// <summary>
/// Provides a chat client implementation that integrates with Azure AI Agents, enabling chat interactions using
/// Azure-specific agent capabilities.
/// </summary>
internal sealed class AzureAIProjectChatClient : DelegatingChatClient
{
    private readonly ChatClientMetadata? _metadata;
    private readonly AIProjectClient _agentClient;
    private readonly AgentVersion? _agentVersion;
    private readonly AgentRecord? _agentRecord;
    private readonly ChatOptions? _chatOptions;
    private readonly AgentReference _agentReference;
    /// <summary>
    /// The usage of a no-op model is a necessary change to avoid OpenAIClients to throw exceptions when
    /// used with Azure AI Agents as the model used is now defined at the agent creation time.
    /// </summary>
    private const string NoOpModel = "no-op";

    /// <summary>
    /// Initializes a new instance of the <see cref="AzureAIProjectChatClient"/> class.
    /// </summary>
    /// <param name="aiProjectClient">An instance of <see cref="AIProjectClient"/> to interact with Azure AI Agents services.</param>
    /// <param name="agentReference">An instance of <see cref="AgentReference"/> representing the specific agent to use.</param>
    /// <param name="defaultModelId">The default model to use for the agent, if applicable.</param>
    /// <param name="chatOptions">An instance of <see cref="ChatOptions"/> representing the options on how the agent was predefined.</param>
    /// <remarks>
    /// The <see cref="IChatClient"/> provided should be decorated with a <see cref="AzureAIProjectChatClient"/> for proper functionality.
    /// </remarks>
    internal AzureAIProjectChatClient(AIProjectClient aiProjectClient, AgentReference agentReference, string? defaultModelId, ChatOptions? chatOptions)
        : base(Throw.IfNull(aiProjectClient)
            .GetProjectOpenAIClient()
            .GetOpenAIResponseClient(defaultModelId ?? NoOpModel)
            .AsIChatClient())
    {
        this._agentClient = aiProjectClient;
        this._agentReference = Throw.IfNull(agentReference);
        this._metadata = new ChatClientMetadata("azure.ai.agents", defaultModelId: defaultModelId);
        this._chatOptions = chatOptions;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AzureAIProjectChatClient"/> class.
    /// </summary>
    /// <param name="aiProjectClient">An instance of <see cref="AIProjectClient"/> to interact with Azure AI Agents services.</param>
    /// <param name="agentRecord">An instance of <see cref="AgentRecord"/> representing the specific agent to use.</param>
    /// <param name="chatOptions">An instance of <see cref="ChatOptions"/> representing the options on how the agent was predefined.</param>
    /// <remarks>
    /// The <see cref="IChatClient"/> provided should be decorated with a <see cref="AzureAIProjectChatClient"/> for proper functionality.
    /// </remarks>
    internal AzureAIProjectChatClient(AIProjectClient aiProjectClient, AgentRecord agentRecord, ChatOptions? chatOptions)
        : this(aiProjectClient, Throw.IfNull(agentRecord).Versions.Latest, chatOptions)
    {
        this._agentRecord = agentRecord;
    }

    internal AzureAIProjectChatClient(AIProjectClient aiProjectClient, AgentVersion agentVersion, ChatOptions? chatOptions)
        : this(
              aiProjectClient,
              new AgentReference(Throw.IfNull(agentVersion).Name, agentVersion.Version),
              (agentVersion.Definition as PromptAgentDefinition)?.Model,
              chatOptions)
    {
        this._agentVersion = agentVersion;
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        return (serviceKey is null && serviceType == typeof(ChatClientMetadata))
            ? this._metadata
            : (serviceKey is null && serviceType == typeof(AIProjectClient))
            ? this._agentClient
            : (serviceKey is null && serviceType == typeof(AgentVersion))
            ? this._agentVersion
            : (serviceKey is null && serviceType == typeof(AgentRecord))
            ? this._agentRecord
            : (serviceKey is null && serviceType == typeof(AgentReference))
            ? this._agentReference
            : base.GetService(serviceType, serviceKey);
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        var agentOptions = this.GetAgentEnabledChatOptions(options);

        return await base.GetResponseAsync(messages, agentOptions, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var agentOptions = this.GetAgentEnabledChatOptions(options);

        await foreach (var chunk in base.GetStreamingResponseAsync(messages, agentOptions, cancellationToken).ConfigureAwait(false))
        {
            yield return chunk;
        }
    }

    private ChatOptions GetAgentEnabledChatOptions(ChatOptions? options)
    {
        // Start with a clone of the base chat options defined for the agent, if any.
        ChatOptions agentEnabledChatOptions = this._chatOptions?.Clone() ?? new();

        // Ignore per-request all options that can't be overridden.
        agentEnabledChatOptions.Instructions = null;
        agentEnabledChatOptions.Tools = null;
        agentEnabledChatOptions.Temperature = null;
        agentEnabledChatOptions.TopP = null;
        agentEnabledChatOptions.PresencePenalty = null;
        agentEnabledChatOptions.ResponseFormat = null;

        // Use the conversation from the request, or the one defined at the client level.
        agentEnabledChatOptions.ConversationId = options?.ConversationId ?? this._chatOptions?.ConversationId;

        // Preserve the original RawRepresentationFactory
        var originalFactory = options?.RawRepresentationFactory;

        agentEnabledChatOptions.RawRepresentationFactory = (client) =>
        {
            if (originalFactory?.Invoke(this) is not ResponseCreationOptions responseCreationOptions)
            {
                responseCreationOptions = new ResponseCreationOptions();
            }

            ResponseCreationOptionsExtensions.set_Agent(responseCreationOptions, this._agentReference);
            ResponseCreationOptionsExtensions.set_Model(responseCreationOptions, null);

            return responseCreationOptions;
        };

        return agentEnabledChatOptions;
    }
}
