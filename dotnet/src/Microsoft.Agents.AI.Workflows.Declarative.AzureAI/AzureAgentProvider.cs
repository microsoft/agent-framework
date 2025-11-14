// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.AI.Projects.OpenAI;
using Azure.Core;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Provides functionality to interact with Foundry agents within a specified project context.
/// </summary>
/// <remarks>This class is used to retrieve and manage AI agents associated with a Foundry project.  It requires a
/// project endpoint and credentials to authenticate requests.</remarks>
/// <param name="projectEndpoint">A <see cref="Uri"/> instance representing the endpoint URL of the Foundry project. This must be a valid, non-null URI pointing to the project.</param>
/// <param name="projectCredentials">The credentials used to authenticate with the Foundry project. This must be a valid instance of <see cref="TokenCredential"/>.</param>
public sealed class AzureAgentProvider(Uri projectEndpoint, TokenCredential projectCredentials) : WorkflowAgentProvider
{
    private readonly Dictionary<string, AgentVersion> _versionCache = [];
    private readonly Dictionary<string, AIAgent> _agentCache = [];

    private AIProjectClient? _agentClient;
    private ProjectConversationsClient? _conversationClient;

    /// <summary>
    /// Optional options used when creating the <see cref="AIProjectClient"/>.
    /// </summary>
    public AIProjectClientOptions? AIProjectClientOptions { get; init; }

    /// <summary>
    /// Optional options used when invoking the <see cref="AIAgent"/>.
    /// </summary>
    public ProjectOpenAIClientOptions? OpenAIClientOptions { get; init; }

    /// <summary>
    /// An optional <see cref="HttpClient"/> instance to be used for making HTTP requests.
    /// If not provided, a default client will be used.
    /// </summary>
    public HttpClient? HttpClient { get; init; }

    /// <inheritdoc/>
    public override async Task<string> CreateConversationAsync(CancellationToken cancellationToken = default)
    {
        ProjectConversation conversation =
            await this.GetConversationClient()
                .CreateProjectConversationAsync(options: null, cancellationToken).ConfigureAwait(false);

        return conversation.Id;
    }

    /// <inheritdoc/>
    public override async Task<ChatMessage> CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default)
    {
        ReadOnlyCollection<ResponseItem> newItems =
            await this.GetConversationClient().CreateProjectConversationItemsAsync(
                conversationId,
                items: GetResponseItems(),
                include: null,
                cancellationToken).ConfigureAwait(false);

        return newItems.AsChatMessages().Single();

        IEnumerable<ResponseItem> GetResponseItems()
        {
            IEnumerable<ChatMessage> messages = [conversationMessage];

            foreach (ResponseItem item in messages.AsOpenAIResponseItems())
            {
                if (string.IsNullOrEmpty(item.Id))
                {
                    yield return item;
                }
                else
                {
                    yield return new ReferenceResponseItem(item.Id);
                }
            }
        }
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<AgentRunResponseUpdate> InvokeAgentAsync(
        string agentId,
        string? agentVersion,
        string? conversationId,
        IEnumerable<ChatMessage>? messages,
        IDictionary<string, object?>? inputArguments,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        AgentVersion agentVersionResult = await this.QueryAgentAsync(agentId, agentVersion, cancellationToken).ConfigureAwait(false);
        AIAgent agent = await this.GetAgentAsync(agentVersionResult, cancellationToken).ConfigureAwait(false);

        ChatOptions chatOptions =
            new()
            {
                ConversationId = conversationId,
                AllowMultipleToolCalls = this.AllowMultipleToolCalls,
            };

        if (inputArguments is not null)
        {
            JsonNode jsonNode = ConvertDictionaryToJson(inputArguments);
            ResponseCreationOptions responseCreationOptions = new();
#pragma warning disable SCME0001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
            responseCreationOptions.Patch.Set("$.structured_inputs"u8, BinaryData.FromString(jsonNode.ToJsonString()));
#pragma warning restore SCME0001 // Type is for evaluation purposes only and is subject to change or removal in future updates. Suppress this diagnostic to proceed.
            chatOptions.RawRepresentationFactory = (_) => responseCreationOptions;
        }

        ChatClientAgentRunOptions runOptions = new(chatOptions);

        IAsyncEnumerable<AgentRunResponseUpdate> agentResponse =
            messages is not null ?
                agent.RunStreamingAsync([.. messages], null, runOptions, cancellationToken) :
                agent.RunStreamingAsync([new ChatMessage(ChatRole.User, string.Empty)], null, runOptions, cancellationToken);

        await foreach (AgentRunResponseUpdate update in agentResponse.ConfigureAwait(false))
        {
            update.AuthorName = agentVersionResult.Name;
            yield return update;
        }
    }

    private async Task<AgentVersion> QueryAgentAsync(string agentName, string? agentVersion, CancellationToken cancellationToken = default)
    {
        string agentKey = $"{agentName}:{agentVersion}";
        if (this._versionCache.TryGetValue(agentKey, out AgentVersion? targetAgent))
        {
            return targetAgent;
        }

        AIProjectClient client = this.GetAgentClient();

        if (string.IsNullOrEmpty(agentVersion))
        {
            AgentRecord agentRecord =
                await client.Agents.GetAgentAsync(
                    agentName,
                    cancellationToken).ConfigureAwait(false);

            targetAgent = agentRecord.Versions.Latest;
        }
        else
        {
            targetAgent =
                await client.Agents.GetAgentVersionAsync(
                    agentName,
                    agentVersion,
                    cancellationToken).ConfigureAwait(false);
        }

        this._versionCache[agentKey] = targetAgent;

        return targetAgent;
    }

    private async Task<AIAgent> GetAgentAsync(AgentVersion agentVersion, CancellationToken cancellationToken = default)
    {
        if (this._agentCache.TryGetValue(agentVersion.Id, out AIAgent? agent))
        {
            return agent;
        }

        AIProjectClient client = this.GetAgentClient();

        agent = client.GetAIAgent(agentVersion, tools: null, clientFactory: null, services: null);

        FunctionInvokingChatClient? functionInvokingClient = agent.GetService<FunctionInvokingChatClient>();
        if (functionInvokingClient is not null)
        {
            // Allow concurrent invocations if configured
            functionInvokingClient.AllowConcurrentInvocation = this.AllowConcurrentInvocation;
            // Allows the caller to respond with function responses
            functionInvokingClient.TerminateOnUnknownCalls = true;
            // Make functions available for execution.  Doesn't change what tool is available for any given agent.
            if (this.Functions is not null)
            {
                if (functionInvokingClient.AdditionalTools is null)
                {
                    functionInvokingClient.AdditionalTools = [.. this.Functions];
                }
                else
                {
                    functionInvokingClient.AdditionalTools = [.. functionInvokingClient.AdditionalTools, .. this.Functions];
                }
            }
        }

        this._agentCache[agentVersion.Id] = agent;

        return agent;
    }

    /// <inheritdoc/>
    public override async Task<ChatMessage> GetMessageAsync(string conversationId, string messageId, CancellationToken cancellationToken = default)
    {
        AgentResponseItem responseItem = await this.GetConversationClient().GetProjectConversationItemAsync(conversationId, messageId, include: null, cancellationToken).ConfigureAwait(false);
        ResponseItem[] items = [responseItem.AsOpenAIResponseItem()];
        return items.AsChatMessages().Single();
    }

    /// <inheritdoc/>
    public override async IAsyncEnumerable<ChatMessage> GetMessagesAsync(
        string conversationId,
        int? limit = null,
        string? after = null,
        string? before = null,
        bool newestFirst = false,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        AgentListOrder order = newestFirst ? AgentListOrder.Ascending : AgentListOrder.Descending;

        await foreach (AgentResponseItem responseItem in this.GetConversationClient().GetProjectConversationItemsAsync(conversationId, null, limit, order.ToString(), after, before, include: null, cancellationToken).ConfigureAwait(false))
        {
            ResponseItem[] items = [responseItem.AsOpenAIResponseItem()];
            foreach (ChatMessage message in items.AsChatMessages())
            {
                yield return message;
            }
        }
    }

    private AIProjectClient GetAgentClient()
    {
        if (this._agentClient is null)
        {
            AIProjectClientOptions clientOptions = this.AIProjectClientOptions ?? new();

            if (this.HttpClient is not null)
            {
                clientOptions.Transport = new HttpClientPipelineTransport(this.HttpClient);
            }

            AIProjectClient newClient = new(projectEndpoint, projectCredentials, clientOptions);

            Interlocked.CompareExchange(ref this._agentClient, newClient, null);
        }

        return this._agentClient;
    }

    private ProjectConversationsClient GetConversationClient()
    {
        if (this._conversationClient is null)
        {
            ProjectConversationsClient conversationClient = this.GetAgentClient().GetProjectOpenAIClient().GetProjectConversationsClient();

            Interlocked.CompareExchange(ref this._conversationClient, conversationClient, null);
        }

        return this._conversationClient;
    }
}
