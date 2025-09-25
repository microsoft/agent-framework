// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Azure.Core.Pipeline;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.AI.Agents;

namespace Microsoft.Agents.Workflows.Declarative;

/// <summary>
/// Provides functionality to interact with Foundry agents within a specified project context.
/// </summary>
/// <remarks>This class is used to retrieve and manage AI agents associated with a Foundry project.  It requires a
/// project endpoint and credentials to authenticate requests.</remarks>
/// <param name="projectEndpoint">The endpoint URL of the Foundry project. This must be a valid, non-null URI pointing to the project.</param>
/// <param name="projectCredentials">The credentials used to authenticate with the Foundry project. This must be a valid instance of <see cref="TokenCredential"/>.</param>
/// <param name="httpClient">An optional <see cref="HttpClient"/> instance to be used for making HTTP requests. If not provided, a default client will be used.</param>
public sealed class AzureAgentProvider(string projectEndpoint, TokenCredential projectCredentials, HttpClient? httpClient = null) : WorkflowAgentProvider
{
    private static readonly Dictionary<string, MessageRole> s_roleMap =
        new()
        {
            [ChatRole.User.Value.ToUpperInvariant()] = MessageRole.User,
            [ChatRole.Assistant.Value.ToUpperInvariant()] = MessageRole.Agent,
            [ChatRole.System.Value.ToUpperInvariant()] = new MessageRole(ChatRole.System.Value),
            [ChatRole.Tool.Value.ToUpperInvariant()] = new MessageRole(ChatRole.Tool.Value),
        };

    private PersistentAgentsClient? _agentsClient;

    /// <inheritdoc/>
    public override async Task<string> CreateConversationAsync(CancellationToken cancellationToken = default)
    {
        PersistentAgentThread conversation = await this.GetAgentsClient().Threads.CreateThreadAsync(cancellationToken: cancellationToken).ConfigureAwait(false);
        return conversation.Id;
    }

    /// <inheritdoc/>
    public override async Task CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default)
    {
        await this.GetAgentsClient().Messages.CreateMessageAsync(
            conversationId,
            role: s_roleMap[conversationMessage.Role.Value.ToUpperInvariant()],
            contentBlocks: GetContent(),
            attachments: null,
            metadata: GetMetadata(),
            cancellationToken).ConfigureAwait(false);

        Dictionary<string, string>? GetMetadata()
        {
            if (conversationMessage.AdditionalProperties is null)
            {
                return null;
            }

            return conversationMessage.AdditionalProperties.ToDictionary(prop => prop.Key, prop => prop.Value?.ToString() ?? string.Empty);
        }

        IEnumerable<MessageInputContentBlock> GetContent()
        {
            foreach (AIContent content in conversationMessage.Contents)
            {
                MessageInputContentBlock? contentBlock =
                    content switch
                    {
                        TextContent textContent => new MessageInputTextBlock(textContent.Text),
                        HostedFileContent fileContent => new MessageInputImageFileBlock(new MessageImageFileParam(fileContent.FileId)),
                        UriContent uriContent when uriContent.Uri is not null => new MessageInputImageUriBlock(new MessageImageUriParam(uriContent.Uri.ToString())),
                        _ => null // Unsupported content type
                    };

                if (contentBlock is not null)
                {
                    yield return contentBlock;
                }
            }
        }
    }

    /// <inheritdoc/>
    public override async Task<AIAgent> GetAgentAsync(string agentId, CancellationToken cancellationToken = default) =>
        await this.GetAgentsClient().GetAIAgentAsync(agentId, chatOptions: null, cancellationToken).ConfigureAwait(false);

    /// <inheritdoc/>
    public override async Task<ChatMessage> GetMessageAsync(string conversationId, string messageId, CancellationToken cancellationToken = default)
    {
        PersistentThreadMessage message = await this.GetAgentsClient().Messages.GetMessageAsync(conversationId, messageId, cancellationToken).ConfigureAwait(false);
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
        ListSortOrder order = newestFirst ? ListSortOrder.Ascending : ListSortOrder.Descending;
        await foreach (PersistentThreadMessage message in this.GetAgentsClient().Messages.GetMessagesAsync(conversationId, runId: null, limit, order, after, before, cancellationToken).ConfigureAwait(false))
        {
            yield return ToChatMessage(message);
        }
    }

    private PersistentAgentsClient GetAgentsClient()
    {
        if (this._agentsClient is null)
        {
            PersistentAgentsAdministrationClientOptions clientOptions = new();

            if (httpClient is not null)
            {
                clientOptions.Transport = new HttpClientTransport(httpClient);
            }

            PersistentAgentsClient newClient = new(projectEndpoint, projectCredentials, clientOptions);

            Interlocked.CompareExchange(ref this._agentsClient, newClient, null);
        }

        return this._agentsClient;
    }

    private static ChatMessage ToChatMessage(PersistentThreadMessage message)
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
