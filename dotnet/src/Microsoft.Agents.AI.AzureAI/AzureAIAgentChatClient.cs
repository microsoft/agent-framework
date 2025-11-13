// Copyright (c) Microsoft. All rights reserved.

using System.ClientModel.Primitives;
using System.Runtime.CompilerServices;
using System.Text;
using Azure.AI.Agents;
using Microsoft.Extensions.AI;
using Microsoft.Shared.Diagnostics;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable OPENAI001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.

namespace Microsoft.Agents.AI.AzureAI;

/// <summary>
/// Provides a chat client implementation that integrates with Azure AI Agents, enabling chat interactions using
/// Azure-specific agent capabilities.
/// </summary>
internal sealed class AzureAIAgentChatClient : DelegatingChatClient
{
    private readonly ChatClientMetadata? _metadata;
    private readonly AgentClient _agentClient;
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
    /// Initializes a new instance of the <see cref="AzureAIAgentChatClient"/> class.
    /// </summary>
    /// <param name="agentClient">An instance of <see cref="AgentClient"/> to interact with Azure AI Agents services.</param>
    /// <param name="agentReference">An instance of <see cref="AgentReference"/> representing the specific agent to use.</param>
    /// <param name="defaultModelId">The default model to use for the agent, if applicable.</param>
    /// <param name="chatOptions">An instance of <see cref="ChatOptions"/> representing the options on how the agent was predefined.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <remarks>
    /// The <see cref="IChatClient"/> provided should be decorated with a <see cref="AzureAIAgentChatClient"/> for proper functionality.
    /// </remarks>
    internal AzureAIAgentChatClient(AgentClient agentClient, AgentReference agentReference, string? defaultModelId, ChatOptions? chatOptions, OpenAIClientOptions? openAIClientOptions = null)
        : base(Throw.IfNull(agentClient)
            .GetOpenAIClient(openAIClientOptions)
            .GetOpenAIResponseClient(defaultModelId ?? NoOpModel)
            .AsIChatClient())
    {
        this._agentClient = agentClient;
        this._agentReference = Throw.IfNull(agentReference);
        this._metadata = new ChatClientMetadata("azure.ai.agents", defaultModelId: defaultModelId);
        this._chatOptions = chatOptions;
    }

    /// <summary>
    /// Initializes a new instance of the <see cref="AzureAIAgentChatClient"/> class.
    /// </summary>
    /// <param name="agentClient">An instance of <see cref="AgentClient"/> to interact with Azure AI Agents services.</param>
    /// <param name="agentRecord">An instance of <see cref="AgentRecord"/> representing the specific agent to use.</param>
    /// <param name="chatOptions">An instance of <see cref="ChatOptions"/> representing the options on how the agent was predefined.</param>
    /// <param name="openAIClientOptions">An optional <see cref="OpenAIClientOptions"/> for configuring the underlying OpenAI client.</param>
    /// <remarks>
    /// The <see cref="IChatClient"/> provided should be decorated with a <see cref="AzureAIAgentChatClient"/> for proper functionality.
    /// </remarks>
    internal AzureAIAgentChatClient(AgentClient agentClient, AgentRecord agentRecord, ChatOptions? chatOptions, OpenAIClientOptions? openAIClientOptions = null)
        : this(agentClient, Throw.IfNull(agentRecord).Versions.Latest, chatOptions, openAIClientOptions)
    {
        this._agentRecord = agentRecord;
    }

    internal AzureAIAgentChatClient(AgentClient agentClient, AgentVersion agentVersion, ChatOptions? chatOptions, OpenAIClientOptions? openAIClientOptions = null)
        : this(
              agentClient,
              new AgentReference(Throw.IfNull(agentVersion).Name) { Version = agentVersion.Version },
              (agentVersion.Definition as PromptAgentDefinition)?.Model,
              chatOptions,
              openAIClientOptions)
    {
        this._agentVersion = agentVersion;
    }

    /// <inheritdoc/>
    public override object? GetService(Type serviceType, object? serviceKey = null)
    {
        return (serviceKey is null && serviceType == typeof(ChatClientMetadata))
            ? this._metadata
            : (serviceKey is null && serviceType == typeof(AgentClient))
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
    public async override IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
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

            this.SetAgentReference(responseCreationOptions);

            return responseCreationOptions;
        };

        return agentEnabledChatOptions;
    }

    // Since the SetAdditionalProperty/SetAgentReference/SetConversationReference extensions in Azure.AI.Agents does not yet support the recent updates in OpenAI 2.6.0
    // The methods below are copied and adapted to the new OpenAI SDK 2.6.0 structure where the Patch property is now exposed directly on ResponseCreationOptions and
    // may be removed once the Azure.AI.Agents package is updated to support OpenAI SDK 2.6+.
#pragma warning disable SCME0001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
    private static void SetAdditionalProperty(ResponseCreationOptions responseCreationOptions, string key, BinaryData value)
    {
        responseCreationOptions.Patch.Set([.. "$."u8, .. Encoding.UTF8.GetBytes(key)], value);
    }

    private void SetAgentReference(ResponseCreationOptions responseCreationOptions)
    {
        SetAdditionalProperty(responseCreationOptions, "agent", ModelReaderWriter.Write(this._agentReference, new ModelReaderWriterOptions("W"), AzureAIAgentsContext.Default));
        responseCreationOptions.Patch.Remove([.. "$."u8, .. Encoding.UTF8.GetBytes("model")]);
    }
#pragma warning restore SCME0001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
}
