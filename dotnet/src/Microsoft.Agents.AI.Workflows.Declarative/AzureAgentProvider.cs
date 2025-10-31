// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Collections.ObjectModel;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents;
using Azure.Core;
using Microsoft.Extensions.AI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Workflows.Declarative;

/// <summary>
/// Provides functionality to interact with Foundry agents within a specified project context.
/// </summary>
/// <remarks>This class is used to retrieve and manage AI agents associated with a Foundry project.  It requires a
/// project endpoint and credentials to authenticate requests.</remarks>
/// <param name="projectEndpoint">The endpoint URL of the Foundry project. This must be a valid, non-null URI pointing to the project.</param>
/// <param name="projectCredentials">The credentials used to authenticate with the Foundry project. This must be a valid instance of <see cref="TokenCredential"/>.</param>
/// <param name="httpClient">An optional <see cref="HttpClient"/> instance to be used for making HTTP requests. If not provided, a default client will be used.</param>
public sealed class AzureAgentProvider(Uri projectEndpoint, TokenCredential projectCredentials, HttpClient? httpClient = null) : WorkflowAgentProvider
{
    private AgentsClient? _agentsClient;

    /// <inheritdoc/>
    public override async Task<string> CreateConversationAsync(CancellationToken cancellationToken = default)
    {
        AgentConversation conversation =
            await this.GetAgentsClient()
                .GetConversationClient()
                .CreateConversationAsync(options: null, cancellationToken).ConfigureAwait(false);

        return conversation.Id;
    }

    /// <inheritdoc/>
    public override async Task<ChatMessage> CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default)
    {
        ChatMessage[] messages = [conversationMessage];

        ReadOnlyCollection<ResponseItem> newItems =
            await this.GetAgentsClient().GetConversationClient().CreateConversationItemsAsync(
                conversationId,
                items: messages.AsOpenAIResponseItems(),
                include: null,
                cancellationToken).ConfigureAwait(false);

        return newItems.AsChatMessages().Single(); // %%% BROKE ASSUMPTION - CARDINALITY
    }

    /// <inheritdoc/>
    public override async Task<AIAgent> GetAgentAsync(string agentId, CancellationToken cancellationToken = default)
    {
        AgentsClient client = this.GetAgentsClient();
        AgentRecord agentRecord =
            await client.GetAgentAsync(
                agentId,
                cancellationToken).ConfigureAwait(false);

        ChatOptions options =
            new()
            {
                AllowMultipleToolCalls = this.AllowMultipleToolCalls,
            };

        AIAgent agent = client.GetAIAgent(agentRecord, options, clientFactory: null, openAIClientOptions: null, cancellationToken);

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

        return agent;
    }

    /// <inheritdoc/>
    public override async Task<ChatMessage> GetMessageAsync(string conversationId, string messageId, CancellationToken cancellationToken = default)
    {
        AgentResponseItem responseItem = await this.GetAgentsClient().GetConversationClient().GetConversationItemAsync(conversationId, messageId, cancellationToken).ConfigureAwait(false);
        ResponseItem[] items = [responseItem.AsOpenAIResponseItem()];
        return items.AsChatMessages().Single(); // %%% BROKE ASSUMPTION - CARDINALITY
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
        AgentsListOrder order = newestFirst ? AgentsListOrder.Asc : AgentsListOrder.Desc;
        await foreach (AgentResponseItem responseItem in this.GetAgentsClient().GetConversationClient().GetConversationItemsAsync(conversationId, limit, order, after, before, itemType: null, cancellationToken).ConfigureAwait(false))
        {
            ResponseItem[] items = [responseItem.AsOpenAIResponseItem()];
            foreach (ChatMessage message in items.AsChatMessages())
            {
                yield return message;
            }
        }
    }

    private AgentsClient GetAgentsClient()
    {
        if (this._agentsClient is null)
        {
            AgentsClientOptions clientOptions = new();

            if (httpClient is not null)
            {
                clientOptions.Transport = new HttpClientPipelineTransport(httpClient);
            }

            AgentsClient newClient = new(projectEndpoint, projectCredentials, clientOptions);

            Interlocked.CompareExchange(ref this._agentsClient, newClient, null);
        }

        return this._agentsClient;
    }
}
