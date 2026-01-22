// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
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

        FormulaValue roleField = result.GetField(TypeSchema.Message.Fields.Role);
        StringValue roleValue = Assert.IsType<StringValue>(roleField);
        Assert.Equal(ChatRole.User.Value, roleValue.Value);
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
        Assert.Contains(result.Fields, f => f.Name == TypeSchema.Message.Fields.Role);

        FormulaValue roleField = result.GetField(TypeSchema.Message.Fields.Role);
        StringValue roleValue = Assert.IsType<StringValue>(roleField);
        Assert.Equal(ChatRole.Assistant.Value, roleValue.Value);
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
        Assert.NotNull(result.GetField(TypeSchema.Discriminator));
        Assert.NotNull(result.GetField(TypeSchema.Message.Fields.Id));
        Assert.NotNull(result.GetField(TypeSchema.Message.Fields.Role));
        Assert.NotNull(result.GetField(TypeSchema.Message.Fields.Content));
        Assert.NotNull(result.GetField(TypeSchema.Message.Fields.Text));
        Assert.NotNull(result.GetField(TypeSchema.Message.Fields.Metadata));
    }

    [Fact]
    public void ToTableWithMultipleMessages()
    {
        // Arrange
        IEnumerable<ChatMessage> messages =
        [
            new(ChatRole.User, "First message"),
            new(ChatRole.Assistant, "Second message"),
            new(ChatRole.User, "Third message")
        ];

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
        IEnumerable<ChatMessage> messages = [];

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
        ChatMessage source = new(ChatRole.User, "Test");
        DataValue record = source.ToRecord().ToDataValue();

        // Act
        IEnumerable<ChatMessage>? result = record.ToChatMessages();

        // Assert
        Assert.NotNull(result);
        ChatMessage message = Assert.Single(result);
        Assert.Equal(source.Role, message.Role);
        Assert.Equal(source.Text, message.Text);
    }

    [Fact]
    public void ToChatMessagesWithTableDataValue()
    {
        // Arrange
        ChatMessage[] source = [new(ChatRole.User, "Test")];
        DataValue table = source.ToTable().ToDataValue();

        // Act
        IEnumerable<ChatMessage>? result = table.ToChatMessages();

        // Assert
        Assert.NotNull(result);
        ChatMessage message = Assert.Single(result);
        Assert.Equal(source[0].Role, message.Role);
        Assert.Equal(source[0].Text, message.Text);
    }

    [Fact]
    public void ToChatMessagesWithTableOfDataValue()
    {
        // Arrange
        TableDataValue table = DataValue.TableFromValues([new StringDataValue("test")]);

        // Act
        IEnumerable<ChatMessage>? result = table.ToChatMessages();

        // Assert
        Assert.NotNull(result);
        ChatMessage message = Assert.Single(result);
        Assert.Equal(ChatRole.User, message.Role);
        Assert.Equal("test", message.Text);
    }

    [Fact]
    public void ToChatMessagesWithUnsupportedValue()
    {
        // Arrange
        BooleanDataValue booleanValue = new(true);

        // Act
        IEnumerable<ChatMessage>? messages = booleanValue.ToChatMessages();

        // Assert
        Assert.Null(messages);
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
    public void ToChatMessageFromDataValueRecord()
    {
        // Arrange
        ChatMessage source = new(ChatRole.User, "Test");
        DataValue record = source.ToRecord().ToDataValue();

        // Act
        ChatMessage? result = record.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.User, result.Role);
        Assert.Equal("Test", result.Text);
    }
    [Fact]
    public void ToChatMessageFromDataValueString()
    {
        // Arrange
        DataValue value = StringDataValue.Create("Test message");

        // Act
        ChatMessage? result = value.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.User, result.Role);
        Assert.Equal("Test message", result.Text);
    }

    [Fact]
    public void ToChatMessageFromBlankDataValue()
    {
        // Arrange
        DataValue value = DataValue.Blank();

        // Act
        ChatMessage? result = value.ToChatMessage();

        // Assert
        Assert.Null(result);
    }

    [Fact]
    public void ToChatMessageFromUnsupportedValue()
    {
        // Arrange
        DataValue value = BooleanDataValue.Create(true);

        // Act & Assert
        Assert.Throws<DeclarativeActionException>(() => value.ToChatMessage());
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
    public void ToChatMessageWithImpliedRole()
    {
        // Arrange
        RecordValue source =
            FormulaValue.NewRecordFromFields(
            new NamedValue(TypeSchema.Message.Fields.Role, FormulaValue.New(string.Empty)),
            new NamedValue(
                TypeSchema.Message.Fields.Content,
                FormulaValue.NewTable(
                    TypeSchema.Message.ContentRecordType,
                     FormulaValue.NewRecordFromFields(
                        new NamedValue(TypeSchema.Message.Fields.ContentType, TypeSchema.Message.ContentTypes.Text.ToFormula()),
                        new NamedValue(TypeSchema.Message.Fields.ContentValue, FormulaValue.New("Test"))))));
        RecordDataValue record = source.ToRecord();

        // Act
        ChatMessage? result = record.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        Assert.Equal(ChatRole.User, result.Role);
        Assert.Equal("Test", result.Text);
    }

    [Fact]
    public void ToChatMessageWithImageUrlContentType()
    {
        // Arrange
        ChatMessage source = new(ChatRole.User, [AgentMessageContentType.ImageUrl.ToContent("https://example.com/image.jpg")!]);
        DataValue record = source.ToRecord().ToDataValue();

        // Act
        ChatMessage? result = record.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        AIContent content = Assert.Single(result.Contents);
        Assert.IsType<UriContent>(content);
    }

    [Fact]
    public void ToChatMessageWithWithImageDataContentType()
    {
        // Arrange
        ChatMessage source = new(ChatRole.User, [AgentMessageContentType.ImageUrl.ToContent("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA")!]);
        DataValue record = source.ToRecord().ToDataValue();

        // Act
        ChatMessage? result = record.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        AIContent content = Assert.Single(result.Contents);
        Assert.IsType<DataContent>(content);
    }

    [Fact]
    public void ToChatMessageWithWithImageFileContentType()
    {
        // Arrange
        ChatMessage source = new(ChatRole.User, [AgentMessageContentType.ImageFile.ToContent("file-id-123")!]);
        DataValue record = source.ToRecord().ToDataValue();

        // Act
        ChatMessage? result = record.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        AIContent content = Assert.Single(result.Contents);
        Assert.IsType<HostedFileContent>(content);
    }

    [Fact]
    public void ToChatMessageWithUnsupportedContent()
    {
        // Arrange
        ChatMessage source = new(ChatRole.User, "Test");
        RecordDataValue record = source.ToRecord().ToRecord();
        DataValue contentValue = record.Properties[TypeSchema.Message.Fields.Content];
        TableDataValue contentValues = Assert.IsType<TableDataValue>(contentValue, exactMatch: false);
        RecordDataValue badContent = DataValue.RecordFromFields(
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.ContentType, StringDataValue.Create(TypeSchema.Message.ContentTypes.Text)),
            new KeyValuePair<string, DataValue>(TypeSchema.Message.Fields.ContentValue, BooleanDataValue.Create(true)));
        contentValues.Values.Add(badContent);

        // Act
        ChatMessage message = record.ToChatMessage();

        // Assert
        Assert.Single(message.Contents);
        Assert.Equal("Test", message.Text);
    }

    [Fact]
    public void ToChatMessageWithEmptyContent()
    {
        // Arrange
        ChatMessage source = new(ChatRole.User, "Test");
        source.Contents.Add(new TextContent(string.Empty));
        RecordDataValue record = source.ToRecord().ToRecord();

        // Act
        ChatMessage message = record.ToChatMessage();

        // Assert
        Assert.Single(message.Contents);
        Assert.Equal("Test", message.Text);
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
    public void ToChatRoleFromAgentMessageRole()
    {
        // Act & Assert
        Assert.Equal(ChatRole.Assistant, AgentMessageRole.Agent.ToChatRole());
        Assert.Equal(ChatRole.User, AgentMessageRole.User.ToChatRole());
        Assert.Equal(ChatRole.User, ((AgentMessageRole)99).ToChatRole());
        Assert.Equal(ChatRole.User, ((AgentMessageRole?)null).ToChatRole());
    }

    [Fact]
    public void AgentMessageContentTypeToContentMissing()
    {
        // Act & Assert
        Assert.Null(AgentMessageContentType.Text.ToContent(string.Empty));
        Assert.Null(AgentMessageContentType.Text.ToContent(null));
    }

    [Fact]
    public void AgentMessageContentTypeToContentText()
    {
        // Arrange & Act
        AIContent? result = AgentMessageContentType.Text.ToContent("Sample text");

        // Assert
        Assert.NotNull(result);
        TextContent textContent = Assert.IsType<TextContent>(result);
        Assert.Equal("Sample text", textContent.Text);
    }

    [Fact]
    public void ToContentWithImageUrlContentType()
    {
        // Arrange & Act
        AIContent? result = AgentMessageContentType.ImageUrl.ToContent("https://example.com/image.jpg");

        // Assert
        Assert.NotNull(result);
        UriContent uriContent = Assert.IsType<UriContent>(result);
        Assert.Equal("https://example.com/image.jpg", uriContent.Uri.ToString());
    }

    [Fact]
    public void ToContentWithImageUrlContentTypeDataUri()
    {
        // Arrange & Act
        AIContent? result = AgentMessageContentType.ImageUrl.ToContent("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA");

        // Assert
        Assert.NotNull(result);
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.False(dataContent.Data.IsEmpty);
    }

    [Fact]
    public void ToContentWithImageFileContentType()
    {
        // Arrange & Act
        AIContent? result = AgentMessageContentType.ImageFile.ToContent("file-id-123");

        // Assert
        Assert.NotNull(result);
        HostedFileContent fileContent = Assert.IsType<HostedFileContent>(result);
        Assert.Equal("file-id-123", fileContent.FileId);
    }

    [Fact]
    public void ToChatMessageFromFunctionResultContents()
    {
        // Arrange
        IEnumerable<FunctionResultContent> functionResults =
            [
                new(callId: "call1", result: "Result 1"),
                new(callId: "call2", result: "Result 2")
            ];

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
        TableDataValue table =
            DataValue.TableFromValues(
                [
                    StringDataValue.Create("Message 1"),
                    StringDataValue.Create("Message 2")
                ]);

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
        ChatMessage message =
            new(ChatRole.User,
                [
                    new TextContent("First part"),
                    new TextContent("Second part")
                ]);

        // Act
        RecordValue result = message.ToRecord();

        // Assert
        Assert.NotNull(result);
        FormulaValue contentField = result.GetField(TypeSchema.Message.Fields.Content);
        TableValue contentTable = Assert.IsType<TableValue>(contentField, exactMatch: false);
        Assert.Equal(2, contentTable.Rows.Count());
    }

    [Fact]
    public void ToRecordWithMessageContainingUriContent()
    {
        // Arrange
        ChatMessage message =
            new(ChatRole.User,
                [
                    new UriContent("https://example.com/image.jpg", "image/*")
                ]);

        // Act
        RecordValue result = message.ToRecord();

        // Assert
        Assert.NotNull(result);
        FormulaValue contentField = result.GetField(TypeSchema.Message.Fields.Content);
        TableValue contentTable = Assert.IsType<TableValue>(contentField, exactMatch: false);
        Assert.Single(contentTable.Rows);
    }

    [Fact]
    public void ToRecordWithMessageContainingHostedFileContent()
    {
        // Arrange
        ChatMessage message =
            new(ChatRole.User,
                [
                    new HostedFileContent("file-123")
                ]);

        // Act
        RecordValue result = message.ToRecord();

        // Assert
        Assert.NotNull(result);
        FormulaValue contentField = result.GetField(TypeSchema.Message.Fields.Content);
        TableValue contentTable = Assert.IsType<TableValue>(contentField, exactMatch: false);
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
        FormulaValue metadataField = result.GetField(TypeSchema.Message.Fields.Metadata);
        RecordValue metadataRecord = Assert.IsType<RecordValue>(metadataField, exactMatch: false);
        Assert.Equal(2, metadataRecord.Fields.Count());
    }

    [Theory]
    [InlineData("data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==", "image/png")]
    [InlineData("data:image/jpeg;base64,/9j/4AAQSkZJRgABAQAAAQABAAD/2wBDAAYEBQYFBAYGBQYHBwYIChAKCgkJChQODwwQFxQYGBcUFhYaHSUfGhsjHBYWICwgIyYnKSopGR8tMC0oMCUoKSj/2wBDAQcHBwoIChMKChMoGhYaKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCgoKCj/wAARCAABAAEDASIAAhEBAxEB/8QAHwAAAQUBAQEBAQEAAAAAAAAAAAECAwQFBgcICQoL/8QAtRAAAgEDAwIEAwUFBAQAAAF9AQIDAAQRBRIhMUEGE1FhByJxFDKBkaEII0KxwRVS0fAkM2JyggkKFhcYGRolJicoKSo0NTY3ODk6Q0RFRkdISUpTVFVWV1hZWmNkZWZnaGlqc3R1dnd4eXqDhIWGh4iJipKTlJWWl5iZmqKjpKWmp6ipqrKztLW2t7i5usLDxMXGx8jJytLT1NXW19jZ2uHi4+Tl5ufo6erx8vP09fb3+Pn6/8QAHwEAAwEBAQEBAQEBAQAAAAAAAAECAwQFBgcICQoL/8QAtREAAgECBAQDBAcFBAQAAQJ3AAECAxEEBSExBhJBUQdhcRMiMoEIFEKRobHBCSMzUvAVYnLRChYkNOEl8RcYGRomJygpKjU2Nzg5OkNERUZHSElKU1RVVldYWVpjZGVmZ2hpanN0dXZ3eHl6goOEhYaHiImKkpOUlbaXmJmaoqOkpaanqKmqsrO0tba3uLm6wsPExcbHyMnK0tPU1dbX2Nna4uPk5ebn6Onq8vP09fb3+Pn6/9oADAMBAAIRAxEAPwD5/ooooA//2Q==", "image/jpeg")]
    [InlineData("data:image/gif;base64,R0lGODlhAQABAAAAACH5BAEKAAEALAAAAAABAAEAAAICTAEAOw==", "image/gif")]
    [InlineData("data:image/webp;base64,UklGRiQAAABXRUJQVlA4IBgAAAAwAQCdASoBAAEAAgA0JaQAA3AA/vuUAAA=", "image/webp")]
    [InlineData("data:image/bmp;base64,Qk0eAAAAAAAAABoAAAAMAAAAAQAAAAEAAAABACAAAAA=", "image/bmp")]
    public void ToContentWithImageDataUri_PreservesMimeType(string dataUri, string expectedMediaType)
    {
        // Arrange & Act
        AIContent? result = AgentMessageContentType.ImageUrl.ToContent(dataUri);

        // Assert
        Assert.NotNull(result);
        DataContent dataContent = Assert.IsType<DataContent>(result);
        Assert.Equal(expectedMediaType, dataContent.MediaType);
        Assert.Equal(dataUri, dataContent.Uri);
    }

    [Theory]
    [InlineData("https://example.com/image.png")]
    [InlineData("https://example.com/photo.jpg")]
    [InlineData("https://example.com/animation.gif")]
    [InlineData("http://test.com/picture.webp")]
    public void ToContentWithImageHttpUri_UsesGenericMimeType(string uri)
    {
        // Arrange & Act
        AIContent? result = AgentMessageContentType.ImageUrl.ToContent(uri);

        // Assert
        Assert.NotNull(result);
        UriContent uriContent = Assert.IsType<UriContent>(result);
        // ChatMessageExtensions.GetImageContent uses "image/*" for all non-data URIs
        Assert.Equal("image/*", uriContent.MediaType);
        Assert.Equal(uri, uriContent.Uri?.ToString());
    }

    [Fact]
    public void ToChatMessageFromRecordWithImageDataUri_PreservesMimeType()
    {
        // Arrange
        const string dataUri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAUA";
        ChatMessage source = new(ChatRole.User, [AgentMessageContentType.ImageUrl.ToContent(dataUri)!]);
        DataValue record = source.ToRecord().ToDataValue();

        // Act
        ChatMessage? result = record.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        AIContent content = Assert.Single(result.Contents);
        DataContent dataContent = Assert.IsType<DataContent>(content);
        Assert.Equal("image/png", dataContent.MediaType);
    }

    [Fact]
    public void ToChatMessageFromRecordWithImageHttpUri_UsesGenericMimeType()
    {
        // Arrange
        const string uri = "https://example.com/test.png";
        ChatMessage source = new(ChatRole.User, [AgentMessageContentType.ImageUrl.ToContent(uri)!]);
        DataValue record = source.ToRecord().ToDataValue();

        // Act
        ChatMessage? result = record.ToChatMessage();

        // Assert
        Assert.NotNull(result);
        AIContent content = Assert.Single(result.Contents);
        UriContent uriContent = Assert.IsType<UriContent>(content);
        Assert.Equal("image/*", uriContent.MediaType);
    }
}
