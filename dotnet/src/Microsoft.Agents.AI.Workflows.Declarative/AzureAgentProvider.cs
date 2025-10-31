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
using Microsoft.Bot.ObjectModel;
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
    private static readonly Dictionary<string, AgentMessageRole> s_roleMap =
        new()
        {
            [ChatRole.User.Value.ToUpperInvariant()] = AgentMessageRole.User,
            [ChatRole.Assistant.Value.ToUpperInvariant()] = AgentMessageRole.Agent,
            [ChatRole.System.Value.ToUpperInvariant()] = AgentMessageRole.Agent, // %%% ??!?!?!?!!!
            [ChatRole.Tool.Value.ToUpperInvariant()] = AgentMessageRole.Agent, // %%% ??!?!?!?!!!
        };

    private AgentsClient? _agentsClient;

    /// <inheritdoc/>
    public override async Task<string> CreateConversationAsync(CancellationToken cancellationToken = default)
    {
        AgentConversationCreationOptions options =
            new()
            {
                Items = { }, // %%% ??!?!?!?!!!
                Metadata = { } // %%% ??!?!?!?!!!
            };

        AgentConversation conversation =
            await this.GetAgentsClient().GetConversationClient().CreateConversationAsync(options, cancellationToken).ConfigureAwait(false);

        return conversation.Id;
    }

    /// <inheritdoc/>
    public override async Task<ChatMessage> CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default)
    {
        IList<ResponseItem> responseItems = [];
        ReadOnlyCollection<ResponseItem> newMessages =
            await this.GetAgentsClient().GetConversationClient().CreateConversationItemsAsync(
                conversationId,
                items: responseItems, // %%% ??!?!?!?!!!
                include: null,
                cancellationToken).ConfigureAwait(false);

        //role: s_roleMap[conversationMessage.Role.Value.ToUpperInvariant()],
        //contentBlocks: GetContent(),
        //attachments: null,
        //metadata: GetMetadata(),

        return ToChatMessage(newMessages[0]); // %%% ??!?!?!?!!!

        //Dictionary<string, string>? GetMetadata()
        //{
        //    if (conversationMessage.AdditionalProperties is null)
        //    {
        //        return null;
        //    }

        //    return conversationMessage.AdditionalProperties.ToDictionary(prop => prop.Key, prop => prop.Value?.ToString() ?? string.Empty);
        //}

        //IEnumerable<MessageInputContentBlock> GetContent()
        //{
        //    foreach (AIContent content in conversationMessage.Contents)
        //    {
        //        MessageInputContentBlock? contentBlock =
        //            content switch
        //            {
        //                TextContent textContent => new MessageInputTextBlock(textContent.Text),
        //                HostedFileContent fileContent => new MessageInputImageFileBlock(new MessageImageFileParam(fileContent.FileId)),
        //                UriContent uriContent when uriContent.Uri is not null => new MessageInputImageUriBlock(new MessageImageUriParam(uriContent.Uri.ToString())),
        //                DataContent dataContent when dataContent.Uri is not null => new MessageInputImageUriBlock(new MessageImageUriParam(dataContent.Uri)),
        //                _ => null // Unsupported content type
        //            };

        //        if (contentBlock is not null)
        //        {
        //            yield return contentBlock;
        //        }
        //    }
        //}
    }

    /// <inheritdoc/>
    public override async Task<AIAgent> GetAgentAsync(string agentId, CancellationToken cancellationToken = default)
    {
        AgentsClient client = this.GetAgentsClient();
        AgentRecord agentRecord =
            await client.GetAgentAsync(
                agentId,
                cancellationToken).ConfigureAwait(false);

        //AllowMultipleToolCalls = this.AllowMultipleToolCalls,// %%% ??!?!?!?!!!

        AIAgent agent = client.GetAIAgent("gpt-4.1", agentRecord, options: null, clientFactory: null, openAIClientOptions: null, cancellationToken);

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
        AgentResponseItem message = await this.GetAgentsClient().GetConversationClient().GetConversationItemAsync(conversationId, messageId, cancellationToken).ConfigureAwait(false);
        return ToChatMessage(message);
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
        await foreach (AgentResponseItem message in this.GetAgentsClient().GetConversationClient().GetConversationItemsAsync(conversationId, limit, order, after, before, itemType: null, cancellationToken).ConfigureAwait(false))
        {
            yield return ToChatMessage(message);
        }
    }

    private AgentsClient GetAgentsClient()
    {
        if (this._agentsClient is null)
        {
            AgentsClientOptions clientOptions = new();

            if (httpClient is not null)
            {
                //clientOptions.Transport = new HttpClientTransport(httpClient); // %%% ??!?!?!?!!!
            }

            AgentsClient newClient = new(projectEndpoint, projectCredentials, clientOptions);

            Interlocked.CompareExchange(ref this._agentsClient, newClient, null);
        }

        return this._agentsClient;
    }

    private static ChatMessage ToChatMessage(AgentResponseItem message)
    {
        return
           new ChatMessage(new ChatRole(message.Role.ToString()), [.. GetContent()])
           {
               MessageId = message.Id,
               CreatedAt = message.CreatedAt,
               AdditionalProperties = GetMetadata()
           };

        IEnumerable<AIContent> GetContent()
        {
            foreach (MessageContent contentItem in message.ContentItems)
            {
                AIContent? content =
                    contentItem switch
                    {
                        MessageTextContent textContent => new TextContent(textContent.Text),
                        MessageImageFileContent imageContent => new HostedFileContent(imageContent.FileId),
                        _ => null // Unsupported content type
                    };

                if (content is not null)
                {
                    yield return content;
                }
            }
        }

        AdditionalPropertiesDictionary? GetMetadata()
        {
            if (message.Metadata is null)
            {
                return null;
            }

            return new AdditionalPropertiesDictionary(message.Metadata.Select(m => new KeyValuePair<string, object?>(m.Key, m.Value)));
        }
    }
}
