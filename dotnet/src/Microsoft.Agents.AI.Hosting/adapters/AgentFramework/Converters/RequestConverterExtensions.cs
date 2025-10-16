using System;
using System.Collections.Generic;
using System.Linq;
using System.Text.Json;

using Azure.AI.AgentsHosting.Ingress.Common.Http.Json;

using AzureAIAgents.Models;

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.Converters;

/// <summary>
/// Extension methods for converting CreateResponse to input messages.
/// </summary>
public static class RequestConverterExtensions
{
    /// <summary>
    /// Extracts input messages from the CreateResponse.
    /// </summary>
    /// <param name="createResponse">The CreateResponse to extract messages from.</param>
    /// <returns>A collection of ChatMessage objects.</returns>
    public static IReadOnlyCollection<ChatMessage> GetInputMessages(this CreateResponse createResponse)
    {
        var items = createResponse.Input.ToObject<IList<ItemParam>>();
        if (items?.Count > 0)
        {
            var messages = items
                .Select(item =>
                    {
                        ChatRole role;
                        IList<ItemContent>? content = null;
                        switch (item)
                        {
                            case ResponsesAssistantMessageItemParam assistantMessage:
                                role = ChatRole.Assistant;
                                content = assistantMessage.Content;
                                break;
                            case ResponsesSystemMessageItemParam systemMessage:
                                role = ChatRole.System;
                                content = systemMessage.Content;
                                break;
                            case ResponsesUserMessageItemParam userMessage:
                                role = ChatRole.User;
                                content = userMessage.Content;
                                break;
                            case UnknownItemParam unknownItem:
                                role = ChatRole.User;
                                unknownItem.TryParseImplicitUserContent(out content);
                                break;
                            default:
                                return null;
                        }

                        var aiContents = (content ?? [])
                            .Select(c => c is ItemContentInputText textContent ? textContent : null)
                            .Where(c => c != null)
                            .Select(AIContent (c) => new TextContent(c!.Text))
                            .ToList();
                        return new ChatMessage(role, aiContents);
                    }
                )
                .Where(m => m != null)
                .ToList();
            return messages as IReadOnlyCollection<ChatMessage>;
        }

        var strMessage = createResponse.Input.ToString();
        return [new ChatMessage(ChatRole.User, strMessage)];
    }

    private static void TryParseImplicitUserContent(this UnknownItemParam item, out IList<ItemContent>? contents)
    {
        if (!item.SerializedAdditionalRawData.TryGetValue("content", out var rawContent))
        {
            contents = null;
            return;
        }

        contents = rawContent.ToObject<List<ItemContent>>() ?? [new ItemContentInputText(rawContent.ToString())];
    }
}
