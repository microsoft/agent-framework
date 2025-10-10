// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Concurrent;
using System.Runtime.CompilerServices;
using System.Text.Json;
using A2A;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Hosting.A2A.Converters;
using Microsoft.Extensions.AI;

namespace AgentWebChat.Web;

internal sealed class A2AAgentClient : AgentClientBase
{
    private readonly ILogger _logger;
    private readonly Uri _uri;

    // because A2A sdk does not provide a client which can handle multiple agents, we need a client per agent
    // for this app the convention is "baseUri/<agentname>"
    private readonly ConcurrentDictionary<string, (A2AClient, A2ACardResolver)> _clients = [];

    public A2AAgentClient(ILogger logger, Uri baseUri)
    {
        this._logger = logger;
        this._uri = baseUri;
    }

    public async override IAsyncEnumerable<AgentRunResponseUpdate> RunStreamingAsync(
        string agentName,
        IList<ChatMessage> messages,
        string? threadId = null,
        [EnumeratorCancellation] CancellationToken cancellationToken = default)
    {
        this._logger.LogInformation("Running agent {AgentName} with {MessageCount} messages via A2A", agentName, messages.Count);

        var (a2aClient, _) = this.ResolveClient(agentName);
        var contextId = threadId ?? Guid.NewGuid().ToString("N");

        // Convert and send messages via A2A without try-catch in yield method
        var results = new List<AgentRunResponseUpdate>();

        try
        {
            // Convert all messages to A2A parts and create a single message
            var parts = messages.ToParts();
            var a2aMessage = new AgentMessage
            {
                MessageId = Guid.NewGuid().ToString("N"),
                ContextId = contextId,
                Role = MessageRole.User,
                Parts = parts
            };

            var messageSendParams = new MessageSendParams { Message = a2aMessage };
            var a2aResponse = await a2aClient.SendMessageAsync(messageSendParams, cancellationToken);

            // Handle different response types
            if (a2aResponse is AgentMessage message)
            {
                var responseMessage = message.ToChatMessage();
                if (responseMessage is not null)
                {
                    results.Add(new AgentRunResponseUpdate(responseMessage.Role, responseMessage.Contents)
                    {
                        MessageId = message.MessageId,
                        CreatedAt = DateTimeOffset.UtcNow
                    });
                }
            }
            else if (a2aResponse is AgentTask agentTask)
            {
                // Manually convert AgentTask artifacts to ChatMessages since the extension method is internal
                if (agentTask.Artifacts is not null)
                {
                    foreach (var artifact in agentTask.Artifacts)
                    {
                        List<AIContent>? aiContents = null;

                        foreach (var part in artifact.Parts)
                        {
                            var aiContent = ConvertPartToAIContent(part);
                            if (aiContent != null)
                            {
                                (aiContents ??= []).Add(aiContent);
                            }
                        }

                        if (aiContents is not null)
                        {
                            var additionalProperties = ConvertMetadataToAdditionalProperties(artifact.Metadata);
                            var chatMessage = new ChatMessage(ChatRole.Assistant, aiContents)
                            {
                                AdditionalProperties = additionalProperties,
                                RawRepresentation = artifact,
                            };

                            results.Add(new AgentRunResponseUpdate(chatMessage.Role, chatMessage.Contents)
                            {
                                MessageId = agentTask.Id,
                                CreatedAt = DateTimeOffset.UtcNow
                            });
                        }
                    }
                }
            }
            else
            {
                this._logger.LogWarning("Unsupported A2A response type: {ResponseType}", a2aResponse?.GetType().FullName ?? "null");
            }
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Error running agent {AgentName} via A2A", agentName);

            results.Add(new AgentRunResponseUpdate(ChatRole.Assistant, $"Error: {ex.Message}")
            {
                MessageId = Guid.NewGuid().ToString("N"),
                CreatedAt = DateTimeOffset.UtcNow
            });
        }

        // Yield the results
        foreach (var result in results)
        {
            yield return result;
        }
    }

    public async override Task<AgentCard?> GetAgentCardAsync(string agentName, CancellationToken cancellationToken = default)
    {
        this._logger.LogInformation("Retrieving agent card for {Agent}", agentName);

        var (_, a2aCardResolver) = this.ResolveClient(agentName);
        try
        {
            return await a2aCardResolver.GetAgentCardAsync(cancellationToken);
        }
        catch (Exception ex)
        {
            this._logger.LogError(ex, "Failed to get agent card for {AgentName}", agentName);
            return null;
        }
    }

    private (A2AClient, A2ACardResolver) ResolveClient(string agentName) =>
        this._clients.GetOrAdd(agentName, name =>
        {
            var uri = new Uri($"{this._uri}/{name}/");
            var a2aClient = new A2AClient(uri);

            // /v1/card is a default path for A2A agent card discovery
            var a2aCardResolver = new A2ACardResolver(uri, agentCardPath: "/v1/card/");

            this._logger.LogInformation("Built clients for agent {Agent} with baseUri {Uri}", name, uri);
            return (a2aClient, a2aCardResolver);
        });

    private static AIContent? ConvertPartToAIContent(Part part) =>
        part switch
        {
            TextPart textPart => new TextContent(textPart.Text)
            {
                RawRepresentation = textPart
            },
            FilePart filePart when filePart.File is FileWithUri fileWithUrl => new HostedFileContent(fileWithUrl.Uri)
            {
                RawRepresentation = filePart
            },
            _ => null
        };

    private static AdditionalPropertiesDictionary? ConvertMetadataToAdditionalProperties(Dictionary<string, JsonElement>? metadata)
    {
        if (metadata is not { Count: > 0 })
        {
            return null;
        }

        var additionalProperties = new AdditionalPropertiesDictionary();
        foreach (var kvp in metadata)
        {
            additionalProperties[kvp.Key] = kvp.Value;
        }
        return additionalProperties;
    }
}

// Extension method to convert multiple chat messages to A2A messages
internal static class ChatMessageExtensions
{
    public static List<AgentMessage> ToA2AMessages(this IList<ChatMessage> chatMessages)
    {
        if (chatMessages is null || chatMessages.Count == 0)
        {
            return [];
        }

        var result = new List<AgentMessage>();
        foreach (var chatMessage in chatMessages)
        {
            result.Add(chatMessage.ToA2AMessage());
        }
        return result;
    }
}
