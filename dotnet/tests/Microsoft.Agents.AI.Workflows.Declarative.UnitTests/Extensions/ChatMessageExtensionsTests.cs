// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Collections.Immutable;
using System.Linq;
using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Extensions.AI;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Extensions;

public sealed class ChatMessageExtensionsTests
{
    [Fact]
    public void ToRecordWithSimpleTextMessage()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Hello World");

        // Act
        RecordValue result = message.ToRecord();

        // Assert
        Assert.NotNull(result);
        Assert.Contains(result.Fields, f => f.Name == TypeSchema.Message.Fields.Role);
        Assert.Contains(result.Fields, f => f.Name == TypeSchema.Message.Fields.Text);

        Dictionary<string, FormulaValue> fields = result.Fields.ToDictionary(f => f.Name, f => f.Value);
        StringValue roleValue = Assert.IsType<StringValue>(fields[TypeSchema.Message.Fields.Role]);
        Assert.Equal("user", roleValue.Value);
    }

    [Fact]
    public void ToRecordWithAssistantMessage()
    {
        // Arrange
        ChatMessage message = new(ChatRole.Assistant, "I can help you");

        // Act
        RecordValue result = message.ToRecord();

        // Assert
        Assert.NotNull(result);
        Dictionary<string, FormulaValue> fields = result.Fields.ToDictionary(f => f.Name, f => f.Value);
        StringValue roleValue = Assert.IsType<StringValue>(fields[TypeSchema.Message.Fields.Role]);
        Assert.Equal("assistant", roleValue.Value);
    }

    [Fact]
    public void ToRecordIncludesAllStandardFields()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Test")
        {
            MessageId = "msg-123"
        };

        // Act
        RecordValue result = message.ToRecord();

        // Assert
        Dictionary<string, FormulaValue> fields = result.Fields.ToDictionary(f => f.Name, f => f.Value);
        Assert.Contains(TypeSchema.Discriminator, fields.Keys);
        Assert.Contains(TypeSchema.Message.Fields.Id, fields.Keys);
        Assert.Contains(TypeSchema.Message.Fields.Role, fields.Keys);
        Assert.Contains(TypeSchema.Message.Fields.Content, fields.Keys);
        Assert.Contains(TypeSchema.Message.Fields.Text, fields.Keys);
        Assert.Contains(TypeSchema.Message.Fields.Metadata, fields.Keys);
    }

    [Fact]
    public void ToTableWithMultipleMessages()
    {
        // Arrange
        IEnumerable<ChatMessage> messages = new List<ChatMessage>
        {
            new(ChatRole.User, "First message"),
            new(ChatRole.Assistant, "Second message"),
            new(ChatRole.User, "Third message")
        };

        // Act
        TableValue result = messages.ToTable();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(3, result.Rows.Count());
    }

    [Fact]
    public void ToTableWithEmptyMessages()
    {
        // Arrange
        IEnumerable<ChatMessage> messages = new List<ChatMessage>();

        // Act
        TableValue result = messages.ToTable();

        // Assert
        Assert.NotNull(result);
        Assert.Empty(result.Rows);
    }

    [Fact]
    public void ToChatMessagesWithNull()
    {
        // Arrange
        DataValue? value = null;

        // Act
        IEnumerable<ChatMessage>? result = value.ToChatMessages();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToChatMessagesWithBlankDataValue()
    {
        // Arrange
        DataValue value = DataValue.Blank();

        // Act
        IEnumerable<ChatMessage>? result = value.ToChatMessages();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToChatMessagesWithStringDataValue()
    {
        // Arrange
        DataValue value = StringDataValue.Create("Hello");

        // Act
        IEnumerable<ChatMessage>? result = value.ToChatMessages();

        // Assert
        Assert.NotNull(result);
        ChatMessage message = Assert.Single(result);
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal("Hello", message.Text);
    }

    [Fact]
    public void ToChatMessagesWithRecordDataValue()
    {
        // Arrange
        RecordDataValue record = DataValue.RecordFromFields(
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.Role, StringDataValue.Create("User")),
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.Content, DataValue.EmptyTable));

        // Act
        IEnumerable<ChatMessage>? result = record.ToChatMessages();

        // Assert
        Assert.NotNull(result);
        ChatMessage message = Assert.Single(result);
        Assert.Equal(ChatRole.User, message.Role);
    }

    [Fact]
    public void ToChatMessageFromStringDataValue()
    {
        // Arrange
        StringDataValue value = StringDataValue.Create("Test message");

        // Act
        ChatMessage result = value.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.User, result.Role);
        Assert.Equal("Test message", result.Text);
    }

    [Fact]
    public void ToChatMessageFromBlankDataValueReturnsNull()
    {
        // Arrange
        DataValue value = DataValue.Blank();

        // Act
        ChatMessage? result = value.ToChatMessage();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToChatMessageFromRecordDataValue()
    {
        // Arrange
        // Note: Use "Agent" not "Assistant" - AgentMessageRole.Agent maps to ChatRole.Assistant
        RecordDataValue record = DataValue.RecordFromFields(
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.Role, StringDataValue.Create("Agent")),
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.Content, DataValue.EmptyTable));

        // Act
        ChatMessage result = record.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.Assistant, result.Role);
    }

    [Fact]
    public void ToMetadataWithNull()
    {
        // Arrange
        RecordDataValue? metadata = null;

        // Act
        AdditionalPropertiesDictionary? result = metadata.ToMetadata();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToMetadataWithProperties()
    {
        // Arrange
        RecordDataValue metadata = DataValue.RecordFromFields(
            new KeyValuePair<string, DataValue>("key1", StringDataValue.Create("value1")),
            new KeyValuePair<string, DataValue>("key2", NumberDataValue.Create(42)));

        // Act
        AdditionalPropertiesDictionary? result = metadata.ToMetadata();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(2, result.Count);
        Assert.Equal("value1", result["key1"]);
        Assert.Equal(42m, result["key2"]);
    }

    [Fact]
    public void ToChatRoleFromAgentMessageRoleAgent()
    {
        // Arrange
        const AgentMessageRole Role = AgentMessageRole.Agent;

        // Act
        ChatRole result = Role.ToChatRole();

        // Assert
        Assert.Equal(ChatRole.Assistant, result);
    }

    [Fact]
    public void ToChatRoleFromAgentMessageRoleUser()
    {
        // Arrange
        const AgentMessageRole Role = AgentMessageRole.User;

        // Act
        ChatRole result = Role.ToChatRole();

        // Assert
        Assert.Equal(ChatRole.User, result);
    }

    [Fact]
    public void ToChatRoleFromNullableAgentMessageRole()
    {
        // Arrange
        AgentMessageRole? role = null;

        // Act
        ChatRole result = role.ToChatRole();

        // Assert
        Assert.Equal(ChatRole.User, result);
    }

    [Fact]
    public void ToChatRoleFromNullableAgentMessageRoleWithValue()
    {
        // Arrange
        AgentMessageRole? role = AgentMessageRole.Agent;

        // Act
        ChatRole result = role.ToChatRole();

        // Assert
        Assert.Equal(ChatRole.Assistant, result);
    }

    [Fact]
    public void ToContentWithNullContentValue()
    {
        // Arrange
        const AgentMessageContentType ContentType = AgentMessageContentType.Text;
        const string? ContentValue = null;

        // Act
        AIContent? result = ContentType.ToContent(ContentValue);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToContentWithEmptyContentValue()
    {
        // Arrange
        const AgentMessageContentType ContentType = AgentMessageContentType.Text;
        const string ContentValue = "";

        // Act
        AIContent? result = ContentType.ToContent(ContentValue);

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToContentWithTextContentType()
    {
        // Arrange
        const AgentMessageContentType ContentType = AgentMessageContentType.Text;
        const string ContentValue = "Sample text";

        // Act
        AIContent? result = ContentType.ToContent(ContentValue);

        // Assert
        Assert.NotNull(result);
        TextContent textContent = Assert.IsType<TextContent>(result);
        Assert.Equal("Sample text", textContent.Text);
    }

    [Fact]
    public void ToContentWithImageUrlContentType()
    {
        // Arrange
        const AgentMessageContentType ContentType = AgentMessageContentType.ImageUrl;
        const string ContentValue = "https://example.com/image.jpg";

        // Act
        AIContent? result = ContentType.ToContent(ContentValue);

        // Assert
        Assert.NotNull(result);
        Assert.IsAssignableFrom<AIContent>(result);
    }

    [Fact]
    public void ToContentWithImageUrlContentTypeDataUri()
    {
        // Arrange
        const AgentMessageContentType ContentType = AgentMessageContentType.ImageUrl;
        const string ContentValue = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA";

        // Act
        AIContent? result = ContentType.ToContent(ContentValue);

        // Assert
        Assert.NotNull(result);
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.False(dataContent.Data.IsEmpty);
    }

    [Fact]
    public void ToContentWithImageFileContentType()
    {
        // Arrange
        const AgentMessageContentType ContentType = AgentMessageContentType.ImageFile;
        const string ContentValue = "file-id-123";

        // Act
        AIContent? result = ContentType.ToContent(ContentValue);

        // Assert
        Assert.NotNull(result);
        HostedFileContent fileContent = Assert.IsType<HostedFileContent>(result);
        Assert.Equal("file-id-123", fileContent.FileId);
    }

    [Fact]
    public void ToChatMessageFromFunctionResultContents()
    {
        // Arrange
        IEnumerable<FunctionResultContent> functionResults = new List<FunctionResultContent>
        {
            new(callId: "call1", result: "Result 1"),
            new(callId: "call2", result: "Result 2")
        };

        // Act
        ChatMessage result = functionResults.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.Tool, result.Role);
        Assert.Equal(2, result.Contents.Count);
    }

    [Fact]
    public void ToChatMessagesFromTableDataValueWithStrings()
    {
        // Arrange
        TableDataValue table = DataValue.TableFromValues(ImmutableArray.Create<DataValue>(
            StringDataValue.Create("Message 1"),
            StringDataValue.Create("Message 2")));

        // Act
        IEnumerable<ChatMessage> result = table.ToChatMessages();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(2, result.Count());
        Assert.All(result, msg => Assert.Equal(ChatRole.User, msg.Role));
    }

    [Fact]
    public void ToChatMessagesFromTableDataValueWithRecords()
    {
        // Arrange
        RecordDataValue record1 = DataValue.RecordFromFields(
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.Role, StringDataValue.Create("User")),
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.Content, DataValue.EmptyTable));

        RecordDataValue record2 = DataValue.RecordFromFields(
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.Role, StringDataValue.Create("Assistant")),
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.Content, DataValue.EmptyTable));

        TableDataValue table = DataValue.TableFromRecords(record1, record2);

        // Act
        IEnumerable<ChatMessage> result = table.ToChatMessages();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(2, result.Count());
    }

    [Fact]
    public void ToChatMessagesFromTableDataValueWithSingleColumnRecords()
    {
        // Arrange
        RecordDataValue innerRecord = DataValue.RecordFromFields(
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.Role, StringDataValue.Create("User")),
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.Content, DataValue.EmptyTable));

        RecordDataValue wrappedRecord = DataValue.RecordFromFields(
            new KeyValuePair<string, DataValue>("Value", innerRecord));

        TableDataValue table = DataValue.TableFromRecords(wrappedRecord);

        // Act
        IEnumerable<ChatMessage> result = table.ToChatMessages();

        // Assert
        Assert.NotNull(result);
        ChatMessage message = Assert.Single(result);
        Assert.Equal(ChatRole.User, message.Role);
    }

    [Fact]
    public void ToRecordWithMessageContainingMultipleContentItems()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, new List<AIContent>
        {
            new TextContent("First part"),
            new TextContent("Second part")
        });

        // Act
        RecordValue result = message.ToRecord();

        // Assert
        Assert.NotNull(result);
        Dictionary<string, FormulaValue> fields = result.Fields.ToDictionary(f => f.Name, f => f.Value);
        TableValue contentTable = Assert.IsType<TableValue>(fields[TypeSchema.Message.Fields.Content], exactMatch: false);
        Assert.Equal(2, contentTable.Rows.Count());
    }

    [Fact]
    public void ToRecordWithMessageContainingUriContent()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, new List<AIContent>
        {
            new UriContent("https://example.com/image.jpg", "image/*")
        });

        // Act
        RecordValue result = message.ToRecord();

        // Assert
        Assert.NotNull(result);
        Dictionary<string, FormulaValue> fields = result.Fields.ToDictionary(f => f.Name, f => f.Value);
        TableValue contentTable = Assert.IsType<TableValue>(fields[TypeSchema.Message.Fields.Content], exactMatch: false);
        Assert.Single(contentTable.Rows);
    }

    [Fact]
    public void ToRecordWithMessageContainingHostedFileContent()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, new List<AIContent>
        {
            new HostedFileContent("file-123")
        });

        // Act
        RecordValue result = message.ToRecord();

        // Assert
        Assert.NotNull(result);
        Dictionary<string, FormulaValue> fields = result.Fields.ToDictionary(f => f.Name, f => f.Value);
        TableValue contentTable = Assert.IsType<TableValue>(fields[TypeSchema.Message.Fields.Content], exactMatch: false);
        Assert.Single(contentTable.Rows);
    }

    [Fact]
    public void ToRecordWithMessageContainingMetadata()
    {
        // Arrange
        ChatMessage message = new(ChatRole.User, "Test message")
        {
            AdditionalProperties = new AdditionalPropertiesDictionary
            {
                ["custom_key"] = "custom_value",
                ["count"] = 5
            }
        };

        // Act
        RecordValue result = message.ToRecord();

        // Assert
        Assert.NotNull(result);
        Dictionary<string, FormulaValue> fields = result.Fields.ToDictionary(f => f.Name, f => f.Value);
        RecordValue metadataRecord = Assert.IsType<RecordValue>(fields[TypeSchema.Message.Fields.Metadata], exactMatch: false);
        Assert.Equal(2, metadataRecord.Fields.Count());
    }
}
