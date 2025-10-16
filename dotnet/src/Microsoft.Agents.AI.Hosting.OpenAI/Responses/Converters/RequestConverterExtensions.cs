// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Text.Json;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Generated.Models;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses.Converters;

/// <summary>
/// Extension methods for converting CreateResponse to input messages.
/// </summary>
internal static class RequestConverterExtensions
{
    /// <summary>
    /// Extracts input messages from the CreateResponse.
    /// </summary>
    /// <param name="createResponse">The CreateResponse to extract messages from.</param>
    /// <param name="jsonSerializerOptions">The JSON serializer options to use for deserialization.</param>
    /// <returns>A collection of ChatMessage objects.</returns>
    public static IReadOnlyCollection<ChatMessage> GetInputMessages(this CreateResponse createResponse, JsonSerializerOptions jsonSerializerOptions)
    {
        var items = createResponse.Input.ToObject<IList<ItemParam>>(jsonSerializerOptions);
        if (items?.Count > 0)
        {
            var messages = new List<ChatMessage>(items.Count);
            foreach (var item in items)
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
                        unknownItem.TryParseImplicitUserContent(out content, jsonSerializerOptions);
                        break;
                    default:
                        continue;
                }

                var aiContents = (content ?? [])
                    .Select(c => c is ItemContentInputText textContent ? textContent : null)
                    .Where(c => c != null)
                    .Select(AIContent (c) => new TextContent(c!.Text))
                    .ToList();
                messages.Add(new ChatMessage(role, aiContents));
            }

            return messages;
        }

        var strMessage = createResponse.Input.ToString();
        return [new ChatMessage(ChatRole.User, strMessage)];
    }

    private static void TryParseImplicitUserContent(this UnknownItemParam item, out IList<ItemContent>? contents, JsonSerializerOptions jsonSerializerOptions)
    {
        if (!item.SerializedAdditionalRawData.TryGetValue("content", out var rawContent))
        {
            contents = null;
            return;
        }

        contents = rawContent.ToObject<List<ItemContent>>(jsonSerializerOptions) ?? [new ItemContentInputText(rawContent.ToString())];
    }
}
