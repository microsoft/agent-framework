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
using Azure.AI.Agents;
using Azure.Core;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
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
/// <param name="httpClient">An optional <see cref="HttpClient"/> instance to be used for making HTTP requests. If not provided, a default client will be used.</param>
public sealed class AzureAgentProvider(Uri projectEndpoint, TokenCredential projectCredentials, HttpClient? httpClient = null) : WorkflowAgentProvider
{
    private readonly Dictionary<string, AgentVersion> _versionCache = [];
    private readonly Dictionary<string, AIAgent> _agentCache = [];

    private AgentClient? _agentClient;
    private ConversationClient? _conversationClient;

    /// <summary>
    /// Optional options used when creating the <see cref="AgentClient"/>.
    /// </summary>
    public AgentClientOptions? ClientOptions { get; init; }

    /// <inheritdoc/>
    public override async Task<string> CreateConversationAsync(CancellationToken cancellationToken = default)
    {
        AgentConversation conversation =
            await this.GetConversationClient()
                .CreateConversationAsync(options: null, cancellationToken).ConfigureAwait(false);

        return conversation.Id;
    }

    /// <inheritdoc/>
    public override async Task<ChatMessage> CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default)
    {
        ReadOnlyCollection<ResponseItem> newItems =
            await this.GetConversationClient().CreateConversationItemsAsync(
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
            JsonNode jsonNode = inputArguments.ToFormula().ToJson();
            ResponseCreationOptions responseCreationOptions = new();
            responseCreationOptions.SetStructuredInputs(BinaryData.FromString(jsonNode.ToJsonString()));
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

        AgentClient client = this.GetAgentClient();

        if (string.IsNullOrEmpty(agentVersion))
        {
            AgentRecord agentRecord =
                await client.GetAgentAsync(
                    agentName,
                    cancellationToken).ConfigureAwait(false);

            targetAgent = agentRecord.Versions.Latest;
        }
        else
        {
            targetAgent =
                await client.GetAgentVersionAsync(
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

        AgentClient client = this.GetAgentClient();

        agent = client.GetAIAgent(agentVersion, tools: null, clientFactory: null, openAIClientOptions: null, services: null, cancellationToken);

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
        AgentResponseItem responseItem = await this.GetConversationClient().GetConversationItemAsync(conversationId, messageId, cancellationToken).ConfigureAwait(false);
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
        await foreach (AgentResponseItem responseItem in this.GetConversationClient().GetConversationItemsAsync(conversationId, limit, order, after, before, itemType: null, cancellationToken).ConfigureAwait(false))
        {
            ResponseItem[] items = [responseItem.AsOpenAIResponseItem()];
            foreach (ChatMessage message in items.AsChatMessages())
            {
                yield return message;
            }
        }
    }

    private AgentClient GetAgentClient()
    {
        if (this._agentClient is null)
        {
            AgentClientOptions clientOptions = this.ClientOptions ?? new();

            if (httpClient is not null)
            {
                clientOptions.Transport = new HttpClientPipelineTransport(httpClient);
            }

            AgentClient newClient = new(projectEndpoint, projectCredentials, clientOptions);

            Interlocked.CompareExchange(ref this._agentClient, newClient, null);
        }

        return this._agentClient;
    }

    private ConversationClient GetConversationClient()
    {
        if (this._conversationClient is null)
        {
            ConversationClient conversationClient = this.GetAgentClient().GetConversationClient();

            Interlocked.CompareExchange(ref this._conversationClient, conversationClient, null);
        }

        return this._conversationClient;
    }
}
