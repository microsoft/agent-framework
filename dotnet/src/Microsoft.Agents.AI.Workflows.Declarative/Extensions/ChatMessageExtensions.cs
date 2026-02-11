// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Agents.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class ChatMessageExtensions
{
    public static RecordValue ToRecord(this ChatMessage message) =>
        FormulaValue.NewRecordFromFields(message.GetMessageFields());

    public static TableValue ToTable(this IEnumerable<ChatMessage> messages) =>
        FormulaValue.NewTable(TypeSchema.Message.RecordType, messages.Select(message => message.ToRecord()));

    public static IEnumerable<ChatMessage>? ToChatMessages(this DataValue? messages)
    {
        if (messages is null or BlankDataValue)
        {
            return null;
        }

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

        return null;
    }

    public static IEnumerable<ChatMessage> ToChatMessages(this TableDataValue messages)
    {
        foreach (RecordDataValue record in messages.Values)
        {
            DataValue sourceRecord = record;
            if (record.Properties.Count == 1 && record.Properties.TryGetValue("Value", out DataValue? singleColumn))
            {
                sourceRecord = singleColumn;
            }
            ChatMessage? convertedMessage = sourceRecord.ToChatMessage();
            if (convertedMessage is not null)
            {
                yield return convertedMessage;
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
            MessageId = message.GetProperty<StringDataValue>(TypeSchema.Message.Fields.Id)?.Value,
            AdditionalProperties = message.GetProperty<RecordDataValue>(TypeSchema.Message.Fields.Metadata).ToMetadata()
        };

    public static ChatMessage ToChatMessage(this StringDataValue message) => new(ChatRole.User, message.Value);

    public static ChatMessage ToChatMessage(this IEnumerable<FunctionResultContent> functionResults) =>
        new(ChatRole.Tool, [.. functionResults]);

    public static AdditionalPropertiesDictionary? ToMetadata(this RecordDataValue? metadata)
    {
        if (metadata is null)
        {
            return null;
        }

        AdditionalPropertiesDictionary properties = [];

        foreach (KeyValuePair<string, DataValue> property in metadata.Properties)
        {
            properties[property.Key] = property.Value.ToObject();
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

    public static AIContent? ToContent(this AgentMessageContentType contentType, string? contentValue, string? mediaType = null)
    {
        if (string.IsNullOrEmpty(contentValue))
        {
            return null;
        }

        return
            contentType switch
            {
                AgentMessageContentType.ImageUrl => GetImageContent(contentValue, mediaType ?? InferMediaType(contentValue)),
                AgentMessageContentType.ImageFile => new HostedFileContent(contentValue),
                _ => new TextContent(contentValue)
            };
    }

    private static ChatRole GetRole(this RecordDataValue message)
    {
        StringDataValue? roleValue = message.GetProperty<StringDataValue>(TypeSchema.Message.Fields.Role);
        if (string.IsNullOrWhiteSpace(roleValue?.Value))
        {
            return ChatRole.User;
        }

        AgentMessageRole? role = null;
        if (Enum.TryParse(roleValue.Value, out AgentMessageRole parsedRole))
        {
            role = parsedRole;
        }

        return role.ToChatRole();
    }

    private static IEnumerable<AIContent> GetContent(this RecordDataValue message)
    {
        TableDataValue? content = message.GetProperty<TableDataValue>(TypeSchema.Message.Fields.Content);
        if (content is not null)
        {
            foreach (RecordDataValue contentItem in content.Values)
            {
                StringDataValue? contentValue = contentItem.GetProperty<StringDataValue>(TypeSchema.MessageContent.Fields.Value);
                StringDataValue? mediaTypeValue = contentItem.GetProperty<StringDataValue>(TypeSchema.MessageContent.Fields.MediaType);
                if (contentValue is null || string.IsNullOrWhiteSpace(contentValue.Value))
                {
                    continue;
                }

                yield return
                    contentItem.GetProperty<StringDataValue>(TypeSchema.MessageContent.Fields.Type)?.Value switch
                    {
                        TypeSchema.MessageContent.ContentTypes.ImageUrl => GetImageContent(contentValue.Value, mediaTypeValue?.Value ?? InferMediaType(contentValue.Value)),
                        TypeSchema.MessageContent.ContentTypes.ImageFile => new HostedFileContent(contentValue.Value),
                        _ => new TextContent(contentValue.Value)
                    };
            }
        }
    }

    private static string InferMediaType(string value)
    {
        // Base64 encoded content includes media type
        if (value.StartsWith("data:", StringComparison.OrdinalIgnoreCase))
        {
            int semicolonIndex = value.IndexOf(';');
            if (semicolonIndex > 5)
            {
                return value.Substring(5, semicolonIndex - 5);
            }
        }

        // URL based input only supports image
        string fileExtension = Path.GetExtension(value);
        return
            fileExtension.ToUpperInvariant() switch
            {
                ".JPG" or ".JPEG" => "image/jpeg",
                ".PNG" => "image/png",
                ".GIF" => "image/gif",
                ".WEBP" => "image/webp",
                _ => "image/*"
            };
    }

    private static AIContent GetImageContent(string uriText, string mediaType) =>
        uriText.StartsWith("data:", StringComparison.OrdinalIgnoreCase) ?
            new DataContent(uriText, mediaType) :
            new UriContent(uriText, mediaType);

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
        yield return new NamedValue(TypeSchema.Discriminator, nameof(ChatMessage).ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Id, message.MessageId.ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Role, message.Role.Value.ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Author, message.AuthorName.ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Content, FormulaValue.NewTable(TypeSchema.MessageContent.RecordType, message.GetContentRecords()));
        yield return new NamedValue(TypeSchema.Message.Fields.Text, message.Text.ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Metadata, message.AdditionalProperties.ToRecord());
    }

    private static IEnumerable<RecordValue> GetContentRecords(this ChatMessage message) =>
        message.Contents.Select(content => FormulaValue.NewRecordFromFields(content.GetContentFields()));

    private static IEnumerable<NamedValue> GetContentFields(this AIContent content)
    {
        return
            content switch
            {
                UriContent uriContent => CreateContentRecord(TypeSchema.MessageContent.ContentTypes.ImageUrl, uriContent.Uri.ToString()),
                HostedFileContent fileContent => CreateContentRecord(TypeSchema.MessageContent.ContentTypes.ImageFile, fileContent.FileId),
                TextContent textContent => CreateContentRecord(TypeSchema.MessageContent.ContentTypes.Text, textContent.Text),
                DataContent dataContent => CreateContentRecord(TypeSchema.MessageContent.ContentTypes.ImageUrl, dataContent.Uri),
                _ => []
            };

        static IEnumerable<NamedValue> CreateContentRecord(string type, string value, string? mediaType = null)
        {
            yield return new NamedValue(TypeSchema.MessageContent.Fields.Type, type.ToFormula());
            yield return new NamedValue(TypeSchema.MessageContent.Fields.Value, value.ToFormula());
            if (mediaType is not null)
            {
                yield return new NamedValue(TypeSchema.MessageContent.Fields.MediaType, mediaType.ToFormula());
            }
        }
    }

    private static RecordValue ToRecord(this AdditionalPropertiesDictionary? value)
    {
        return FormulaValue.NewRecordFromFields(GetFields());

        IEnumerable<NamedValue> GetFields()
        {
            if (value is not null)
            {
                foreach (string key in value.Keys)
                {
                    yield return new NamedValue(key, value[key].ToFormula());
                }
            }
        }
    }
}
