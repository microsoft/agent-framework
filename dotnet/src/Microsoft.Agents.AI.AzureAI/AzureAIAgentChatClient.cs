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
    private readonly AgentVersion _agentVersion;
    private readonly ChatOptions? _chatOptions;

    /// <summary>
    /// The usage of a no-op model is a necessary change to avoid OpenAIClients to throw exceptions when
    /// used with Azure AI Agents as the model used is now defined at the agent creation time.
    /// </summary>
    private const string NoOpModel = "no-op";

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
    }

    internal AzureAIAgentChatClient(AgentClient agentClient, AgentVersion agentVersion, ChatOptions? chatOptions, OpenAIClientOptions? openAIClientOptions = null)
        : base(agentClient
            .GetOpenAIClient(openAIClientOptions)
            .GetOpenAIResponseClient((agentVersion.Definition as PromptAgentDefinition)?.Model ?? NoOpModel)
            .AsIChatClient())
    {
        this._agentClient = Throw.IfNull(agentClient);
        this._agentVersion = Throw.IfNull(agentVersion);
        this._metadata = new ChatClientMetadata("azure.ai.agents");
        this._chatOptions = chatOptions;
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
            : base.GetService(serviceType, serviceKey);
    }

    /// <inheritdoc/>
    public override async Task<ChatResponse> GetResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, CancellationToken cancellationToken = default)
    {
        var conversationId = await this.GetOrCreateConversationAsync(options, cancellationToken).ConfigureAwait(false);
        var conversationChatOptions = this.GetConversationEnabledChatOptions(options, conversationId);

        return await base.GetResponseAsync(messages, conversationChatOptions, cancellationToken).ConfigureAwait(false);
    }

    /// <inheritdoc/>
    public async override IAsyncEnumerable<ChatResponseUpdate> GetStreamingResponseAsync(IEnumerable<ChatMessage> messages, ChatOptions? options = null, [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        var conversation = await this.GetOrCreateConversationAsync(options, cancellationToken).ConfigureAwait(false);
        var conversationOptions = this.GetConversationEnabledChatOptions(options, conversation);

        await foreach (var chunk in base.GetStreamingResponseAsync(messages, conversationOptions, cancellationToken).ConfigureAwait(false))
        {
            yield return chunk;
        }
    }

    private async Task<string> GetOrCreateConversationAsync(ChatOptions? options, CancellationToken cancellationToken)
        => string.IsNullOrWhiteSpace(options?.ConversationId)
            ? (await this._agentClient.GetConversationClient().CreateConversationAsync(cancellationToken: cancellationToken).ConfigureAwait(false)).Value.Id
            : options.ConversationId;

    private ChatOptions GetConversationEnabledChatOptions(ChatOptions? chatOptions, string conversationId)
    {
        // Start with a clone of the base chat options defined for the agent, if any.
        ChatOptions conversationChatOptions = this._chatOptions?.Clone() ?? new();

        // Ignore per-request all options that can't be overridden.
        conversationChatOptions.Instructions = null;
        conversationChatOptions.Tools = null;

        // Preserve the original RawRepresentationFactory
        var originalFactory = chatOptions?.RawRepresentationFactory;

        conversationChatOptions.RawRepresentationFactory = (client) =>
        {
            if (originalFactory?.Invoke(this) is not ResponseCreationOptions responseCreationOptions)
            {
                responseCreationOptions = new ResponseCreationOptions();
            }

            SetAgentReference(responseCreationOptions, this._agentVersion);
            SetConversationReference(responseCreationOptions, conversationId);

            return responseCreationOptions;
        };

        return conversationChatOptions;
    }

    // Since the SetAdditionalProperty/SetAgentReference/SetConversationReference extensions in Azure.AI.Agents does not yet support the recent updates in OpenAI 2.6.0
    // The methods below are copied and adapted to the new OpenAI SDK 2.6.0 structure where the Patch property is now exposed directly on ResponseCreationOptions and
    // may be removed once the Azure.AI.Agents package is updated to support OpenAI SDK 2.6+.
#pragma warning disable SCME0001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
    private static void SetAdditionalProperty(ResponseCreationOptions responseCreationOptions, string key, BinaryData value)
    {
        responseCreationOptions.Patch.Set([.. "$."u8, .. Encoding.UTF8.GetBytes(key)], value);
    }

    private static void SetAgentReference(ResponseCreationOptions responseCreationOptions, AgentVersion agentVersion)
    {
        var agentReference = new AgentReference(agentVersion.Name) { Version = agentVersion.Version };

        SetAdditionalProperty(responseCreationOptions, "agent", ModelReaderWriter.Write(agentReference, new ModelReaderWriterOptions("W"), AzureAIAgentsContext.Default));
        responseCreationOptions.Patch.Remove([.. "$."u8, .. Encoding.UTF8.GetBytes("model")]);
    }

    private static void SetConversationReference(ResponseCreationOptions responseCreationOptions, string conversationId)
    {
        SetAdditionalProperty(responseCreationOptions, "conversation", BinaryData.FromString($"\"{conversationId}\""));
    }
#pragma warning restore SCME0001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
}
