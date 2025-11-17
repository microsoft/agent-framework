// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.OpenAI.Tests;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Tests for the newly added content type event generators:
/// - ErrorContentEventGenerator
/// - ImageContentEventGenerator
/// - AudioContentEventGenerator
/// - HostedFileContentEventGenerator
/// - FileContentEventGenerator
/// </summary>
public sealed class ContentTypeEventGeneratorTests : ConformanceTestBase
{
    #region TextReasoningContent Tests

    [Fact]
    public async Task TextReasoningContent_GeneratesReasoningItem_SuccessAsync()
    {
        // Arrange
        const string AgentName = "reasoning-content-agent";
        const string ExpectedText = "The first 10 prime numbers are: 2, 3, 5, 7, 11, 13, 17, 19, 23, and 29. Adding these together, we get:\n\n2 + 3 + 5 + 7 + 11 + 13 + 17 + 19 + 23 + 29 = 129\n\nSo, the sum of the first 10 prime numbers is 129.";
        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a reasoning agent.", ExpectedText, (msg) =>
        [
            new TextReasoningContent(string.Empty), // Reasoning content is emitted but not included in the output text
            new TextContent(ExpectedText)
        ]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        Assert.NotEmpty(events);

        // Verify first item is reasoning item
        var firstItemAddedEvent = events.First(e => e.GetProperty("type").GetString() == "response.output_item.added");
        var firstItem = firstItemAddedEvent.GetProperty("item");
        Assert.Equal("reasoning", firstItem.GetProperty("type").GetString());
        Assert.True(firstItemAddedEvent.GetProperty("output_index").GetInt32() == 0);

        // Verify reasoning item done
        var firstItemDoneEvent = events.First(e =>
            e.GetProperty("type").GetString() == "response.output_item.done" &&
            e.GetProperty("output_index").GetInt32() == 0);
        var firstItemDone = firstItemDoneEvent.GetProperty("item");
        Assert.Equal("reasoning", firstItemDone.GetProperty("type").GetString());

        // Verify second item is message with text
        var secondItemAddedEvent = events.First(e =>
            e.GetProperty("type").GetString() == "response.output_item.added" &&
            e.GetProperty("output_index").GetInt32() == 1);
        var secondItem = secondItemAddedEvent.GetProperty("item");
        Assert.Equal("message", secondItem.GetProperty("type").GetString());
    }

    [Fact]
    public async Task TextReasoningContent_EmitsCorrectEventSequence_SuccessAsync()
    {
        // Arrange
        const string AgentName = "reasoning-sequence-agent";
        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a reasoning agent.", "Result", (msg) =>
        [
            new TextReasoningContent("reasoning step"),
            new TextContent("Result")
        ]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert - Verify event sequence
        List<string?> eventTypes = events.ConvertAll(e => e.GetProperty("type").GetString());

        Assert.Equal("response.created", eventTypes[0]);
        Assert.Equal("response.in_progress", eventTypes[1]);

        // First reasoning item
        int reasoningItemAdded = eventTypes.IndexOf("response.output_item.added");
        Assert.True(reasoningItemAdded >= 0);

        // Reasoning item should be done immediately after being added (no deltas)
        int reasoningItemDone = eventTypes.FindIndex(reasoningItemAdded, e => e == "response.output_item.done");
        Assert.True(reasoningItemDone > reasoningItemAdded);

        // Then message item
        int messageItemAdded = eventTypes.FindIndex(reasoningItemDone, e => e == "response.output_item.added");
        Assert.True(messageItemAdded > reasoningItemDone);
    }

    [Fact]
    public async Task TextReasoningContent_OutputIndexIncremented_SuccessAsync()
    {
        // Arrange
        const string AgentName = "reasoning-index-agent";
        HttpClient client = await this.CreateTestServerAsync(AgentName, "You are a reasoning agent.", "Answer", (msg) =>
        [
            new TextReasoningContent("thinking..."),
            new TextContent("Answer")
        ]);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert - Verify output indices
        var itemAddedEvents = events.Where(e => e.GetProperty("type").GetString() == "response.output_item.added").ToList();

        // Should have 2 items: reasoning at index 0, message at index 1
        Assert.Equal(2, itemAddedEvents.Count);
        Assert.Equal(0, itemAddedEvents[0].GetProperty("output_index").GetInt32());
        Assert.Equal(1, itemAddedEvents[1].GetProperty("output_index").GetInt32());

        // First item should be reasoning
        Assert.Equal("reasoning", itemAddedEvents[0].GetProperty("item").GetProperty("type").GetString());
        // Second item should be message
        Assert.Equal("message", itemAddedEvents[1].GetProperty("item").GetProperty("type").GetString());
    }

    #endregion
    // Streaming request JSON for OpenAI Responses API
    private const string StreamingRequestJson = @"{""model"":""gpt-4o-mini"",""input"":""test"",""stream"":true}";

    #region ErrorContent Tests

    [Fact]
    public async Task ErrorContent_GeneratesRefusalItem_SuccessAsync()
    {
        // Arrange
        const string AgentName = "error-content-agent";
        const string ErrorMessage = "I cannot assist with that request.";
        HttpClient client = await this.CreateErrorContentAgentAsync(AgentName, ErrorMessage);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        Assert.NotEmpty(events);

        // Verify item added event
        var itemAddedEvent = events.FirstOrDefault(e => e.GetProperty("type").GetString() == "response.output_item.added");
        Assert.True(itemAddedEvent.ValueKind != JsonValueKind.Undefined);

        var item = itemAddedEvent.GetProperty("item");
        Assert.Equal("message", item.GetProperty("type").GetString());

        // Verify content contains refusal
        var content = item.GetProperty("content");
        Assert.Equal(JsonValueKind.Array, content.ValueKind);

        var contentArray = content.EnumerateArray().ToList();
        Assert.NotEmpty(contentArray);

        var refusalContent = contentArray.First(c => c.GetProperty("type").GetString() == "refusal");
        Assert.True(refusalContent.ValueKind != JsonValueKind.Undefined);
        Assert.Equal(ErrorMessage, refusalContent.GetProperty("refusal").GetString());
    }

    [Fact]
    public async Task ErrorContent_EmitsCorrectEventSequence_SuccessAsync()
    {
        // Arrange
        const string AgentName = "error-sequence-agent";
        const string ErrorMessage = "Access denied.";
        HttpClient client = await this.CreateErrorContentAgentAsync(AgentName, ErrorMessage);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert - Verify event sequence
        List<string?> eventTypes = events.ConvertAll(e => e.GetProperty("type").GetString());

        Assert.Equal("response.created", eventTypes[0]);
        Assert.Equal("response.in_progress", eventTypes[1]);
        Assert.Contains("response.output_item.added", eventTypes);
        Assert.Contains("response.content_part.added", eventTypes);
        Assert.Contains("response.content_part.done", eventTypes);
        Assert.Contains("response.output_item.done", eventTypes);
        Assert.Contains("response.completed", eventTypes);

        // Verify ordering
        int itemAdded = eventTypes.IndexOf("response.output_item.added");
        int partAdded = eventTypes.IndexOf("response.content_part.added");
        int partDone = eventTypes.IndexOf("response.content_part.done");
        int itemDone = eventTypes.IndexOf("response.output_item.done");

        Assert.True(itemAdded < partAdded);
        Assert.True(partAdded < partDone);
        Assert.True(partDone < itemDone);
    }

    [Fact]
    public async Task ErrorContent_SequenceNumbersAreCorrect_SuccessAsync()
    {
        // Arrange
        const string AgentName = "error-seq-num-agent";
        HttpClient client = await this.CreateErrorContentAgentAsync(AgentName, "Error message");

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert - Sequence numbers are sequential
        List<int> sequenceNumbers = events.ConvertAll(e => e.GetProperty("sequence_number").GetInt32());
        Assert.NotEmpty(sequenceNumbers);

        for (int i = 0; i < sequenceNumbers.Count; i++)
        {
            Assert.Equal(i, sequenceNumbers[i]);
        }
    }

    #endregion

    #region ImageContent Tests

    [Fact]
    public async Task ImageContent_UriContent_GeneratesImageItem_SuccessAsync()
    {
        // Arrange
        const string AgentName = "image-uri-agent";
        const string ImageUrl = "https://example.com/image.jpg";
        HttpClient client = await this.CreateImageContentAgentAsync(AgentName, ImageUrl, isDataUri: false);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        var itemAddedEvent = events.FirstOrDefault(e => e.GetProperty("type").GetString() == "response.output_item.added");
        Assert.True(itemAddedEvent.ValueKind != JsonValueKind.Undefined);

        var content = itemAddedEvent.GetProperty("item").GetProperty("content");
        var imageContent = content.EnumerateArray().First(c => c.GetProperty("type").GetString() == "input_image");

        Assert.True(imageContent.ValueKind != JsonValueKind.Undefined);
        Assert.Equal(ImageUrl, imageContent.GetProperty("image_url").GetString());
    }

    [Fact]
    public async Task ImageContent_DataContent_GeneratesImageItem_SuccessAsync()
    {
        // Arrange
        const string AgentName = "image-data-agent";
        const string DataUri = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==";
        HttpClient client = await this.CreateImageContentAgentAsync(AgentName, DataUri, isDataUri: true);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        var itemAddedEvent = events.FirstOrDefault(e => e.GetProperty("type").GetString() == "response.output_item.added");
        Assert.True(itemAddedEvent.ValueKind != JsonValueKind.Undefined);

        var content = itemAddedEvent.GetProperty("item").GetProperty("content");
        var imageContent = content.EnumerateArray().First(c => c.GetProperty("type").GetString() == "input_image");

        Assert.True(imageContent.ValueKind != JsonValueKind.Undefined);
        Assert.Equal(DataUri, imageContent.GetProperty("image_url").GetString());
    }

    [Fact]
    public async Task ImageContent_WithDetailProperty_IncludesDetail_SuccessAsync()
    {
        // Arrange
        const string AgentName = "image-detail-agent";
        const string ImageUrl = "https://example.com/image.jpg";
        const string Detail = "high";
        HttpClient client = await this.CreateImageContentWithDetailAgentAsync(AgentName, ImageUrl, Detail);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        var itemAddedEvent = events.FirstOrDefault(e => e.GetProperty("type").GetString() == "response.output_item.added");
        Assert.True(itemAddedEvent.ValueKind != JsonValueKind.Undefined);

        var content = itemAddedEvent.GetProperty("item").GetProperty("content");
        var imageContent = content.EnumerateArray().First(c => c.GetProperty("type").GetString() == "input_image");

        Assert.True(imageContent.ValueKind != JsonValueKind.Undefined);
        Assert.True(imageContent.TryGetProperty("detail", out var detailProp));
        Assert.Equal(Detail, detailProp.GetString());
    }

    [Fact]
    public async Task ImageContent_EmitsCorrectEventSequence_SuccessAsync()
    {
        // Arrange
        const string AgentName = "image-sequence-agent";
        HttpClient client = await this.CreateImageContentAgentAsync(AgentName, "https://example.com/test.png", isDataUri: false);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        List<string?> eventTypes = events.ConvertAll(e => e.GetProperty("type").GetString());

        Assert.Contains("response.output_item.added", eventTypes);
        Assert.Contains("response.content_part.added", eventTypes);
        Assert.Contains("response.content_part.done", eventTypes);
        Assert.Contains("response.output_item.done", eventTypes);
    }

    #endregion

    #region AudioContent Tests

    [Fact]
    public async Task AudioContent_Mp3Format_GeneratesAudioItem_SuccessAsync()
    {
        // Arrange
        const string AgentName = "audio-mp3-agent";
        const string AudioDataUri = "data:audio/mpeg;base64,/+MYxAAAAAAAAAAAAAAAAAAAAAAASW5mbwAAAA8AAAACAAADhAC7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7u7v/////////////////////////////////////////////////////////////////";
        HttpClient client = await this.CreateAudioContentAgentAsync(AgentName, AudioDataUri, "audio/mpeg");

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        var itemAddedEvent = events.FirstOrDefault(e => e.GetProperty("type").GetString() == "response.output_item.added");
        Assert.True(itemAddedEvent.ValueKind != JsonValueKind.Undefined);

        var content = itemAddedEvent.GetProperty("item").GetProperty("content");
        var audioContent = content.EnumerateArray().First(c => c.GetProperty("type").GetString() == "input_audio");

        Assert.True(audioContent.ValueKind != JsonValueKind.Undefined);
        Assert.Equal(AudioDataUri, audioContent.GetProperty("data").GetString());
        Assert.Equal("mp3", audioContent.GetProperty("format").GetString());
    }

    [Fact]
    public async Task AudioContent_WavFormat_GeneratesCorrectFormat_SuccessAsync()
    {
        // Arrange
        const string AgentName = "audio-wav-agent";
        const string AudioDataUri = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAAB9AAACABAAZGF0YQAAAAA=";
        HttpClient client = await this.CreateAudioContentAgentAsync(AgentName, AudioDataUri, "audio/wav");

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        var itemAddedEvent = events.FirstOrDefault(e => e.GetProperty("type").GetString() == "response.output_item.added");
        var content = itemAddedEvent.GetProperty("item").GetProperty("content");
        var audioContent = content.EnumerateArray().First(c => c.GetProperty("type").GetString() == "input_audio");

        Assert.Equal("wav", audioContent.GetProperty("format").GetString());
    }

    [Theory]
    [InlineData("audio/opus", "opus")]
    [InlineData("audio/aac", "aac")]
    [InlineData("audio/flac", "flac")]
    [InlineData("audio/pcm", "pcm16")]
    [InlineData("audio/unknown", "mp3")] // Default fallback
    public async Task AudioContent_VariousFormats_GeneratesCorrectFormat_SuccessAsync(string mediaType, string expectedFormat)
    {
        // Arrange
        const string AgentName = "audio-format-agent";
        const string AudioDataUri = "data:audio/test;base64,AQIDBA==";
        HttpClient client = await this.CreateAudioContentAgentAsync(AgentName, AudioDataUri, mediaType);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        var itemAddedEvent = events.FirstOrDefault(e => e.GetProperty("type").GetString() == "response.output_item.added");
        var content = itemAddedEvent.GetProperty("item").GetProperty("content");
        var audioContent = content.EnumerateArray().First(c => c.GetProperty("type").GetString() == "input_audio");

        Assert.Equal(expectedFormat, audioContent.GetProperty("format").GetString());
    }

    #endregion

    #region HostedFileContent Tests

    [Fact]
    public async Task HostedFileContent_GeneratesFileItem_SuccessAsync()
    {
        // Arrange
        const string AgentName = "hosted-file-agent";
        const string FileId = "file-abc123";
        HttpClient client = await this.CreateHostedFileContentAgentAsync(AgentName, FileId);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        var itemAddedEvent = events.FirstOrDefault(e => e.GetProperty("type").GetString() == "response.output_item.added");
        Assert.True(itemAddedEvent.ValueKind != JsonValueKind.Undefined);

        var content = itemAddedEvent.GetProperty("item").GetProperty("content");
        var fileContent = content.EnumerateArray().First(c => c.GetProperty("type").GetString() == "input_file");

        Assert.True(fileContent.ValueKind != JsonValueKind.Undefined);
        Assert.Equal(FileId, fileContent.GetProperty("file_id").GetString());
    }

    [Fact]
    public async Task HostedFileContent_EmitsCorrectEventSequence_SuccessAsync()
    {
        // Arrange
        const string AgentName = "hosted-file-sequence-agent";
        HttpClient client = await this.CreateHostedFileContentAgentAsync(AgentName, "file-xyz789");

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        List<string?> eventTypes = events.ConvertAll(e => e.GetProperty("type").GetString());

        Assert.Contains("response.output_item.added", eventTypes);
        Assert.Contains("response.content_part.added", eventTypes);
        Assert.Contains("response.content_part.done", eventTypes);
        Assert.Contains("response.output_item.done", eventTypes);
    }

    #endregion

    #region FileContent Tests

    [Fact]
    public async Task FileContent_WithDataUri_GeneratesFileItem_SuccessAsync()
    {
        // Arrange
        const string AgentName = "file-data-agent";
        const string FileDataUri = "data:application/pdf;base64,JVBERi0xLjQKJeLjz9MK";
        const string Filename = "document.pdf";
        HttpClient client = await this.CreateFileContentAgentAsync(AgentName, FileDataUri, Filename);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        var itemAddedEvent = events.FirstOrDefault(e => e.GetProperty("type").GetString() == "response.output_item.added");
        Assert.True(itemAddedEvent.ValueKind != JsonValueKind.Undefined);

        var content = itemAddedEvent.GetProperty("item").GetProperty("content");
        var fileContent = content.EnumerateArray().First(c => c.GetProperty("type").GetString() == "input_file");

        Assert.True(fileContent.ValueKind != JsonValueKind.Undefined);
        Assert.Equal(FileDataUri, fileContent.GetProperty("file_data").GetString());
        Assert.Equal(Filename, fileContent.GetProperty("filename").GetString());
    }

    [Fact]
    public async Task FileContent_WithoutFilename_GeneratesFileItemWithoutFilename_SuccessAsync()
    {
        // Arrange
        const string AgentName = "file-no-name-agent";
        const string FileDataUri = "data:application/json;base64,eyJ0ZXN0IjoidmFsdWUifQ==";
        HttpClient client = await this.CreateFileContentAgentAsync(AgentName, FileDataUri, null);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        var itemAddedEvent = events.FirstOrDefault(e => e.GetProperty("type").GetString() == "response.output_item.added");
        var content = itemAddedEvent.GetProperty("item").GetProperty("content");
        var fileContent = content.EnumerateArray().First(c => c.GetProperty("type").GetString() == "input_file");

        Assert.True(fileContent.ValueKind != JsonValueKind.Undefined);
        Assert.Equal(FileDataUri, fileContent.GetProperty("file_data").GetString());
        // filename property might be null or absent
    }

    #endregion

    #region Mixed Content Tests

    [Fact]
    public async Task MixedContent_TextAndImage_GeneratesMultipleItems_SuccessAsync()
    {
        // Arrange
        const string AgentName = "mixed-text-image-agent";
        HttpClient client = await this.CreateMixedContentAgentAsync(AgentName);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        var itemAddedEvents = events.Where(e => e.GetProperty("type").GetString() == "response.output_item.added").ToList();

        // Should have at least 2 items (text and image)
        Assert.True(itemAddedEvents.Count >= 2, $"Expected at least 2 items, got {itemAddedEvents.Count}");
    }

    [Fact]
    public async Task MixedContent_ErrorAndText_GeneratesMultipleItems_SuccessAsync()
    {
        // Arrange
        const string AgentName = "mixed-error-text-agent";
        HttpClient client = await this.CreateErrorAndTextContentAgentAsync(AgentName);

        // Act
        HttpResponseMessage httpResponse = await this.SendResponsesRequestAsync(client, AgentName, StreamingRequestJson);
        string sseContent = await httpResponse.Content.ReadAsStringAsync();
        var events = ParseSseEvents(sseContent);

        // Assert
        var itemAddedEvents = events.Where(e => e.GetProperty("type").GetString() == "response.output_item.added").ToList();

        // Should have multiple items
        Assert.True(itemAddedEvents.Count >= 2);
    }

    #endregion

    #region Helper Methods

    private static List<JsonElement> ParseSseEvents(string sseContent)
    {
        var events = new List<JsonElement>();
        var lines = sseContent.Split('\n');

        for (int i = 0; i < lines.Length; i++)
        {
            var line = lines[i].TrimEnd('\r');

            if (line.StartsWith("event: ", StringComparison.Ordinal) && i + 1 < lines.Length)
            {
                var dataLine = lines[i + 1].TrimEnd('\r');
                if (dataLine.StartsWith("data: ", StringComparison.Ordinal))
                {
                    var jsonData = dataLine.Substring("data: ".Length);
                    var doc = JsonDocument.Parse(jsonData);
                    events.Add(doc.RootElement.Clone());
                }
            }
        }

        return events;
    }

    private async Task<HttpClient> CreateErrorContentAgentAsync(string agentName, string errorMessage)
    {
        return await this.CreateTestServerAsync(agentName, "You are a test agent.", string.Empty, (msg) =>
            [new ErrorContent(errorMessage)]);
    }

    private async Task<HttpClient> CreateImageContentAgentAsync(string agentName, string imageUri, bool isDataUri)
    {
        return await this.CreateTestServerAsync(agentName, "You are a test agent.", string.Empty, (msg) =>
        {
            if (isDataUri)
            {
                return [new DataContent(imageUri, "image/png")];
            }

            return [new UriContent(imageUri, "image/jpeg")];
        });
    }

    private async Task<HttpClient> CreateImageContentWithDetailAgentAsync(string agentName, string imageUri, string detail)
    {
        return await this.CreateTestServerAsync(agentName, "You are a test agent.", string.Empty, (msg) =>
        {
            var uriContent = new UriContent(imageUri, "image/jpeg")
            {
                AdditionalProperties = new AdditionalPropertiesDictionary { ["detail"] = detail }
            };
            return [uriContent];
        });
    }

    private async Task<HttpClient> CreateAudioContentAgentAsync(string agentName, string audioDataUri, string mediaType)
    {
        return await this.CreateTestServerAsync(agentName, "You are a test agent.", string.Empty, (msg) =>
            [new DataContent(audioDataUri, mediaType)]);
    }

    private async Task<HttpClient> CreateHostedFileContentAgentAsync(string agentName, string fileId)
    {
        return await this.CreateTestServerAsync(agentName, "You are a test agent.", string.Empty, (msg) =>
            [new HostedFileContent(fileId)]);
    }

    private async Task<HttpClient> CreateFileContentAgentAsync(string agentName, string fileDataUri, string? filename)
    {
        // Extract media type from data URI
        string mediaType = "application/pdf"; // default
        if (fileDataUri.StartsWith("data:", StringComparison.Ordinal))
        {
            int semicolonIndex = fileDataUri.IndexOf(';');
            if (semicolonIndex > 5)
            {
                mediaType = fileDataUri.Substring(5, semicolonIndex - 5);
            }
        }
        return await this.CreateTestServerAsync(agentName, "You are a test agent.", string.Empty, (msg) =>
            [new DataContent(fileDataUri, mediaType) { Name = filename }]);
    }

    private async Task<HttpClient> CreateMixedContentAgentAsync(string agentName)
    {
        return await this.CreateTestServerAsync(agentName, "You are a test agent.", string.Empty, (msg) =>
        [
            new TextContent("Here is an image:"),
            new UriContent("https://example.com/image.png", "image/png")
        ]);
    }

    private async Task<HttpClient> CreateErrorAndTextContentAgentAsync(string agentName)
    {
        return await this.CreateTestServerAsync(agentName, "You are a test agent.", string.Empty, (msg) =>
        [
            new TextContent("I need to inform you:"),
            new ErrorContent("The requested operation is not allowed.")
        ]);
    }

    #endregion
}
