// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Linq;
using System.Net.Http;
using System.Runtime.CompilerServices;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Agents.Persistent;
using Azure.Core;
using Azure.Core.Pipeline;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.Declarative;

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
        PersistentAgentThread conversation =
            await this.GetAgentsClient().Threads.CreateThreadAsync(
                messages: null,
                toolResources: null,
                metadata: null,
                cancellationToken).ConfigureAwait(false);

        return conversation.Id;
    }

    /// <inheritdoc/>
    public override Task<ChatMessage> CreateMessageAsync(string conversationId, ChatMessage conversationMessage, CancellationToken cancellationToken = default)
    {
        // TODO: Switch to asynchronous "CreateMessageAsync", when fix properly applied:
        //  BUG: https://github.com/Azure/azure-sdk-for-net/issues/52571
        //   PR: https://github.com/Azure/azure-sdk-for-net/pull/52653
        PersistentThreadMessage newMessage =
            this.GetAgentsClient().Messages.CreateMessage(
                conversationId,
                role: s_roleMap[conversationMessage.Role.Value.ToUpperInvariant()],
                contentBlocks: GetContent(),
                attachments: null,
                metadata: GetMetadata(),
                cancellationToken);

        return Task.FromResult(ToChatMessage(newMessage));

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
                        DataContent dataContent when dataContent.Uri is not null => new MessageInputImageUriBlock(new MessageImageUriParam(dataContent.Uri)),
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
    public override async Task<AIAgent> GetAgentAsync(string agentId, CancellationToken cancellationToken = default)
    {
        ChatClientAgentOptions agentOptions =
            new()
            {
                ChatOptions =
                    new ChatOptions()
                    {
                        AllowMultipleToolCalls = true,
                    },
            };

        PersistentAgentsClient foundryClient = this.GetAgentsClient();
        PersistentAgent foundryAgent = await foundryClient.Administration.GetAgentAsync(agentId, cancellationToken).ConfigureAwait(false);
        if (foundryAgent.Tools.Any(tool => tool is FunctionToolDefinition))
        {
            agentOptions.ChatOptions.Tools = [.. new MenuPlugin().GetTools().Select(t => t.AsDeclarationOnly())]; // %%% TOOL: HAXX - REMOVE
            // %%% TOOL: DESCRIBE
            //IEnumerable<AITool> tools = foundryAgent.Tools.OfType<FunctionToolDefinition>().Select(tool => tool.AsAITool());
            //IEnumerable<AITool> tools = [];
        }
        IChatClient chatClient = foundryClient.AsIChatClient(agentId, defaultThreadId: null); // %%% TOOL: REDUNDANT ROUNDTRIP
        ChatClientAgent agent = new(chatClient, agentOptions, loggerFactory: null, services: null);
        FunctionInvokingChatClient? functionInvokingClient = agent.GetService<FunctionInvokingChatClient>();
        if (functionInvokingClient is not null)
        {
            functionInvokingClient.TerminateOnUnknownCalls = true;
            functionInvokingClient.AllowConcurrentInvocation = true;
        }
        return agent;
    }

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

internal sealed class MenuPlugin // %%% TOOL: HAXX - REMOVE
{
    public IEnumerable<AIFunction> GetTools()
    {
        yield return AIFunctionFactory.Create(this.GetMenu); // %%% , $"{nameof(MenuPlugin)}_{nameof(GetMenu)}");
        yield return AIFunctionFactory.Create(this.GetSpecials); // %%% , $"{nameof(MenuPlugin)}_{nameof(GetSpecials)}");
        yield return AIFunctionFactory.Create(this.GetItemPrice); // %%% , $"{nameof(MenuPlugin)}_{nameof(GetItemPrice)}");
    }

    [Description("Provides a list items on the menu.")]
    public MenuItem[] GetMenu()
    {
        return s_menuItems;
    }

    [Description("Provides a list of specials from the menu.")]
    public MenuItem[] GetSpecials()
    {
        return [.. s_menuItems.Where(i => i.IsSpecial)];
    }

    [Description("Provides the price of the requested menu item.")]
    public float? GetItemPrice(
        [Description("The name of the menu item.")]
        string menuItem)
    {
        return s_menuItems.FirstOrDefault(i => i.Name.Equals(menuItem, StringComparison.OrdinalIgnoreCase))?.Price;
    }

    private static readonly MenuItem[] s_menuItems =
        [
            new()
            {
                Category = "Soup",
                Name = "Clam Chowder",
                Price = 4.95f,
                IsSpecial = true,
            },
            new()
            {
                Category = "Soup",
                Name = "Tomato Soup",
                Price = 4.95f,
                IsSpecial = false,
            },
            new()
            {
                Category = "Salad",
                Name = "Cobb Salad",
                Price = 9.99f,
            },
            new()
            {
                Category = "Salad",
                Name = "House Salad",
                Price = 4.95f,
            },
            new()
            {
                Category = "Drink",
                Name = "Chai Tea",
                Price = 2.95f,
                IsSpecial = true,
            },
            new()
            {
                Category = "Drink",
                Name = "Soda",
                Price = 1.95f,
            },
        ];

    public sealed class MenuItem
    {
        public string Category { get; init; } = string.Empty;
        public string Name { get; init; } = string.Empty;
        public float Price { get; init; }
        public bool IsSpecial { get; init; }
    }
}
