// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Agents.Workflows.Declarative.PowerFx.Functions;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class ChatMessageExtensions
{
    public static RecordValue ToRecord(this ChatMessage message) =>
        FormulaValue.NewRecordFromFields(message.GetMessageFields());

    public static TableValue ToTable(this IEnumerable<ChatMessage> messages) =>
        FormulaValue.NewTable(s_messageRecordType, messages.Select(message => message.ToRecord()));

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
                if (record.Properties.Count == 1 && record.Properties.TryGetValue("Value", out DataValue? singleColumn))
                {
                    record = singleColumn as RecordDataValue ?? record;
                }
                ChatMessage? convertedMessage = record.ToChatMessage();
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
        StringDataValue? roleValue = message.GetProperty<StringDataValue>(TypeSchema.Message.Fields.Role);
        if (roleValue is null || string.IsNullOrWhiteSpace(roleValue.Value))
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
                StringDataValue? contentValue = contentItem?.GetProperty<StringDataValue>(TypeSchema.Message.Fields.ContentValue);
                if (contentValue is null || string.IsNullOrWhiteSpace(contentValue.Value))
                {
                    continue;
                }
                yield return
                    contentItem?.GetProperty<StringDataValue>(TypeSchema.Message.Fields.ContentType)?.Value switch
                    {
                        TypeSchema.Message.ContentTypes.ImageUrl => new UriContent(contentValue.Value, "image/*"),
                        TypeSchema.Message.ContentTypes.ImageFile => new HostedFileContent(contentValue.Value),
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
        yield return new NamedValue(TypeSchema.Message.Fields.Id, message.MessageId.ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Role, message.Role.Value.ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Author, message.AuthorName.ToFormula());
        yield return new NamedValue(TypeSchema.Message.Fields.Content, FormulaValue.NewTable(s_contentRecordType, message.GetContentRecords()));
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
                UriContent uriContent => CreateContentRecord(TypeSchema.Message.ContentTypes.ImageUrl, uriContent.Uri.ToString()),
                HostedFileContent fileContent => CreateContentRecord(TypeSchema.Message.ContentTypes.ImageFile, fileContent.FileId),
                TextContent textContent => CreateContentRecord(TypeSchema.Message.ContentTypes.Text, textContent.Text),
                _ => []
            };

        static IEnumerable<NamedValue> CreateContentRecord(string type, string value)
        {
            yield return new NamedValue(TypeSchema.Message.Fields.ContentType, type.ToFormula());
            yield return new NamedValue(TypeSchema.Message.Fields.ContentValue, value.ToFormula());
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

    private static readonly RecordType s_contentRecordType =
        RecordType.Empty()
            .Add(TypeSchema.Message.Fields.ContentType, FormulaType.String)
            .Add(TypeSchema.Message.Fields.ContentValue, FormulaType.String);

    private static readonly RecordType s_messageRecordType =
        RecordType.Empty()
            .Add(TypeSchema.Message.Fields.Id, FormulaType.String)
            .Add(TypeSchema.Message.Fields.Role, FormulaType.String)
            .Add(TypeSchema.Message.Fields.Author, FormulaType.String)
            .Add(TypeSchema.Message.Fields.Content, s_contentRecordType.ToTable())
            .Add(TypeSchema.Message.Fields.Text, FormulaType.String)
            .Add(TypeSchema.Message.Fields.Metadata, RecordType.Empty());
}
