// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Azure.AI.Agents.Persistent;
using Microsoft.Agents.Workflows.Declarative.PowerFx.Functions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class ChatMessageExtensions
{
    public static RecordValue ToRecord(this ChatMessage message) =>
        RecordValue.NewRecordFromFields(message.GetMessageFields());

    public static TableValue ToTable(this IEnumerable<ChatMessage> messages) =>
        FormulaValue.NewTable(null!, messages.Select(message => message.ToRecord()));

    public static IEnumerable<ChatMessage> ToChatMessages(this DataValue messages)
    {
        if (messages is TableDataValue table)
        {
            return table.ToChatMessages();
        }

        if (messages is RecordDataValue record)
        {
            return [record.ToChatMessage()];
        }

        if (messages is StringDataValue text)
        {
            return [text.ToChatMessage()];
        }

        return [];
    }

    public static IEnumerable<ChatMessage> ToChatMessages(this TableDataValue messages)
    {
        foreach (DataValue message in messages.Values)
        {
            if (message is RecordDataValue record)
            {
                ChatMessage? convertedMessage = record.Properties["Value"].ToChatMessage();
                if (convertedMessage is not null)
                {
                    yield return convertedMessage;
                }
            }
            else if (message is StringDataValue text)
            {
                yield return ToChatMessage(text);
            }
        }
    }

    public static ChatMessage? ToChatMessage(this DataValue message)
    {
        if (message is RecordDataValue record)
        {
            return record.ToChatMessage();
        }

        if (message is StringDataValue text)
        {
            return text.ToChatMessage();
        }

        if (message is BlankDataValue)
        {
            return null;
        }

        throw new DeclarativeActionException($"Unable to convert {message.GetDataType()} to {nameof(ChatMessage)}.");
    }

    public static ChatMessage ToChatMessage(this RecordDataValue message) =>
        new(message.GetRole(), [.. message.GetContent()])
        {
            AdditionalProperties = message.GetProperty<RecordDataValue>("metadata").ToMetadata()
        };

    public static ChatMessage ToChatMessage(this StringDataValue message) => new(ChatRole.User, message.Value);

    public static ChatMessage ToChatMessage(this PersistentThreadMessage message)
    {
        return
           new ChatMessage(new ChatRole(message.Role.ToString()), [.. GetContent()])
           {
               AdditionalProperties = GetMetadata()
           };

        IEnumerable<AIContent> GetContent() // %%% TODO
        {
            //foreach (MessageContent itemContent in message.ContentItems)
            //{
            //    // Process text content
            //    if (itemContent is MessageTextContent textContent)
            //    {
            //        content.Items.Add(new TextContent(textContent.Text));

            //        foreach (MessageTextAnnotation annotation in textContent.Annotations)
            //        {
            //            AnnotationContent? annotationItem = GenerateAnnotationContent(annotation);
            //            if (annotationItem != null)
            //            {
            //                content.Items.Add(annotationItem);
            //            }
            //            else
            //            {
            //                logger?.LogAzureAIAgentUnknownAnnotation(nameof(GenerateMessageContent), message.RunId, message.ThreadId, annotation.GetType());
            //            }
            //        }
            //    }
            //    // Process image content
            //    else if (itemContent is MessageImageFileContent imageContent)
            //    {
            //        content.Items.Add(new FileReferenceContent(imageContent.FileId));
            //    }
            //}
            yield break;
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

    public static AdditionalPropertiesDictionary? ToMetadata(this RecordDataValue? metadata)
    {
        if (metadata is null)
        {
            return null;
        }

        AdditionalPropertiesDictionary properties = [];

        foreach (KeyValuePair<string, DataValue> property in metadata.Properties)
        {
            properties[property.Key] = property.Value.ToFormulaValue().ToObject();
        }

        return properties;
    }

    public static ChatRole ToChatRole(this AgentMessageRole role) =>
        role switch
        {
            AgentMessageRole.Agent => ChatRole.Assistant,
            AgentMessageRole.User => ChatRole.User,
            _ => ChatRole.User
        };

    public static ChatRole ToChatRole(this AgentMessageRole? role) => role?.ToChatRole() ?? ChatRole.User;

    public static AIContent? ToContent(this AgentMessageContentType contentType, string? contentValue)
    {
        if (string.IsNullOrEmpty(contentValue))
        {
            return null;
        }

        return
            contentType switch
            {
                AgentMessageContentType.ImageUrl => new UriContent(contentValue, "image/*"),
                AgentMessageContentType.ImageFile => new HostedFileContent(contentValue),
                _ => new TextContent(contentValue)
            };
    }

    private static ChatRole GetRole(this RecordDataValue message)
    {
        StringDataValue? roleValue = message.GetProperty<StringDataValue>(UserMessage.Fields.Role);
        if (roleValue is null || string.IsNullOrWhiteSpace(roleValue.Value))
        {
            return ChatRole.User;
        }

        AgentMessageRole? role = null;
        if (Enum.TryParse<AgentMessageRole>(roleValue.Value, out AgentMessageRole parsedRole))
        {
            role = parsedRole;
        }

        return role.ToChatRole();
    }

    private static IEnumerable<AIContent> GetContent(this RecordDataValue message)
    {
        TableDataValue? content = message.GetProperty<TableDataValue>(UserMessage.Fields.Content);
        if (content is not null)
        {
            foreach (RecordDataValue contentItem in content.Values)
            {
                StringDataValue? contentValue = contentItem?.GetProperty<StringDataValue>(UserMessage.Fields.ContentValue);
                if (contentValue is null || string.IsNullOrWhiteSpace(contentValue.Value))
                {
                    continue;
                }
                yield return
                    contentItem?.GetProperty<StringDataValue>(UserMessage.Fields.ContentType)?.Value switch
                    {
                        UserMessage.ContentTypes.ImageUrl => new UriContent(contentValue.Value, "image/*"),
                        UserMessage.ContentTypes.ImageFile => new HostedFileContent(contentValue.Value),
                        _ => new TextContent(contentValue.Value)
                    };
            }
        }
    }

    private static TValue? GetProperty<TValue>(this RecordDataValue record, string name)
        where TValue : DataValue
    {
        if (record.Properties.TryGetValue(name, out DataValue? value) && value is TValue dataValue)
        {
            return dataValue;
        }

        return null;
    }

    private static IEnumerable<NamedValue> GetMessageFields(this ChatMessage message)
    {
        yield return new NamedValue(UserMessage.Fields.Id, message.MessageId.ToFormulaValue());
        yield return new NamedValue(UserMessage.Fields.Role, message.Role.Value.ToFormulaValue());
        yield return new NamedValue(UserMessage.Fields.Author, message.AuthorName.ToFormulaValue());

        ChatResponse? rawMessage = message.RawRepresentation as ChatResponse; // %%% IS VALID ???
        if (rawMessage is not null)
        {
            yield return new NamedValue(UserMessage.Fields.ConversationId, rawMessage.ConversationId.ToFormulaValue());
            //yield return new NamedValue(UserMessage.Fields.AgentId, rawMessage.???.ToFormulaValue());
            //yield return new NamedValue(UserMessage.Fields.RunId, rawMessage.???.ToFormulaValue());
        }

        yield return new NamedValue(UserMessage.Fields.Content, TableValue.NewTable(s_contentRecordType, message.GetContentRecords()));
        yield return new NamedValue(UserMessage.Fields.Metadata, message.AdditionalProperties.ToFormulaValue());
    }

    private static IEnumerable<RecordValue> GetContentRecords(this ChatMessage message) =>
        message.Contents.Select(content => RecordValue.NewRecordFromFields(content.GetContentFields()));

    private static IEnumerable<NamedValue> GetContentFields(this AIContent content)
    {
        return
            content switch
            {
                UriContent uriContent => CreateContentRecord(UserMessage.ContentTypes.ImageUrl, uriContent.Uri.ToString()),
                HostedFileContent fileContent => CreateContentRecord(UserMessage.ContentTypes.ImageFile, fileContent.FileId),
                TextContent textContent => CreateContentRecord(UserMessage.ContentTypes.Text, textContent.Text),
                _ => []
            };

        static IEnumerable<NamedValue> CreateContentRecord(string type, string value) // %%% ENUM ???
        {
            yield return new NamedValue(UserMessage.Fields.ContentType, type.ToFormulaValue());
            yield return new NamedValue(UserMessage.Fields.ContentValue, value.ToFormulaValue());
        }
    }

    private static readonly RecordType s_contentRecordType =
        RecordType.Empty()
            .Add(UserMessage.Fields.ContentType, FormulaType.String) // %%% ENUM ???
            .Add(UserMessage.Fields.ContentValue, FormulaType.String);
}
