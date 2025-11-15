// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Agents.AI.DurableTask.State;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask.Tests.Unit.State;

public sealed class DurableAgentStateContentTests
{
    private static readonly JsonTypeInfo s_stateContentTypeInfo =
        DurableAgentStateJsonContext.Default.GetTypeInfo(typeof(DurableAgentStateContent))!;

    [Fact]
    public void ErrorContentSerializationDeserialization()
    {
        // Arrange
        ErrorContent errorContent = new("message")
        {
            Details = "details",
            ErrorCode = "code"
        };

        DurableAgentStateContent durableContent = DurableAgentStateContent.FromAIContent(errorContent);

        // Act
        string jsonContent = JsonSerializer.Serialize(durableContent, s_stateContentTypeInfo);

        DurableAgentStateContent? convertedJsonContent =
            (DurableAgentStateContent?)JsonSerializer.Deserialize(jsonContent, s_stateContentTypeInfo);

        // Assert
        Assert.NotNull(convertedJsonContent);

        AIContent convertedContent = convertedJsonContent.ToAIContent();

        ErrorContent convertedErrorContent = Assert.IsType<ErrorContent>(convertedContent);

        Assert.Equal(errorContent.Message, convertedErrorContent.Message);
        Assert.Equal(errorContent.Details, convertedErrorContent.Details);
        Assert.Equal(errorContent.ErrorCode, convertedErrorContent.ErrorCode);
    }

    [Fact]
    public void TextContentSerializationDeserialization()
    {
        // Arrange
        TextContent textContent = new("Hello, world!");

        DurableAgentStateContent durableContent = DurableAgentStateContent.FromAIContent(textContent);

        // Act
        string jsonContent = JsonSerializer.Serialize(durableContent, s_stateContentTypeInfo);

        DurableAgentStateContent? convertedJsonContent =
            (DurableAgentStateContent?)JsonSerializer.Deserialize(jsonContent, s_stateContentTypeInfo);

        // Assert
        Assert.NotNull(convertedJsonContent);

        AIContent convertedContent = convertedJsonContent.ToAIContent();

        TextContent convertedTextContent = Assert.IsType<TextContent>(convertedContent);

        Assert.Equal(textContent.Text, convertedTextContent.Text);
    }

    [Fact]
    public void FunctionCallContentSerializationDeserialization()
    {
        // Arrange
        FunctionCallContent functionCallContent = new(
            "call-123",
            "MyFunction",
            new Dictionary<string, object?>
            {
                { "param1", 42 },
                { "param2", "value" }
            });

        DurableAgentStateContent durableContent = DurableAgentStateContent.FromAIContent(functionCallContent);

        // Act
        string jsonContent = JsonSerializer.Serialize(durableContent, s_stateContentTypeInfo);

        DurableAgentStateContent? convertedJsonContent =
            (DurableAgentStateContent?)JsonSerializer.Deserialize(jsonContent, s_stateContentTypeInfo);

        // Assert
        Assert.NotNull(convertedJsonContent);

        AIContent convertedContent = convertedJsonContent.ToAIContent();

        FunctionCallContent convertedFunctionCallContent = Assert.IsType<FunctionCallContent>(convertedContent);

        Assert.Equal(functionCallContent.CallId, convertedFunctionCallContent.CallId);
        Assert.Equal(functionCallContent.Name, convertedFunctionCallContent.Name);

        Assert.NotNull(functionCallContent.Arguments);
        Assert.NotNull(convertedFunctionCallContent.Arguments);
        Assert.Equal(functionCallContent.Arguments.Keys.Order(), convertedFunctionCallContent.Arguments.Keys.Order());

        // NOTE: Deserialized dictionaries will have JSON element values rather than the original native types,
        // so we only check the keys here.
        foreach (string key in functionCallContent.Arguments.Keys)
        {
            Assert.Equal(
                JsonSerializer.Serialize(functionCallContent.Arguments[key]),
                JsonSerializer.Serialize(convertedFunctionCallContent.Arguments[key]));
        }
    }

    [Fact]
    public void FunctionResultContentSerializationDeserialization()
    {
        // Arrange
        FunctionResultContent functionResultContent = new("call-123", "return value");

        DurableAgentStateContent durableContent = DurableAgentStateContent.FromAIContent(functionResultContent);

        // Act
        string jsonContent = JsonSerializer.Serialize(durableContent, s_stateContentTypeInfo);

        DurableAgentStateContent? convertedJsonContent =
            (DurableAgentStateContent?)JsonSerializer.Deserialize(jsonContent, s_stateContentTypeInfo);

        // Assert
        Assert.NotNull(convertedJsonContent);

        AIContent convertedContent = convertedJsonContent.ToAIContent();

        FunctionResultContent convertedFunctionResultContent = Assert.IsType<FunctionResultContent>(convertedContent);

        Assert.Equal(functionResultContent.CallId, convertedFunctionResultContent.CallId);
        // NOTE: We serialize both results to JSON for comparison since deserialized objects will be
        // JSON elements rather than the original native types.
        Assert.Equal(
            JsonSerializer.Serialize(functionResultContent.Result),
            JsonSerializer.Serialize(convertedFunctionResultContent.Result));
    }

    [Theory]
    [InlineData("data:text/plain;base64,SGVsbG8sIFdvcmxkIQ==", null)] // Valid data URI containing media type; pass null for separate mediaType parameter.
    [InlineData("data:;base64,SGVsbG8sIFdvcmxkIQ==", "text/plain")] // Valid data URI without media type; pass media
    public void DataContentSerializationDeserialization(string dataUri, string? mediaType)
    {
        // Arrange
        DataContent dataContent = new(dataUri, mediaType);

        DurableAgentStateContent durableContent = DurableAgentStateContent.FromAIContent(dataContent);

        // Act
        string jsonContent = JsonSerializer.Serialize(durableContent, s_stateContentTypeInfo);

        DurableAgentStateContent? convertedJsonContent =
            (DurableAgentStateContent?)JsonSerializer.Deserialize(jsonContent, s_stateContentTypeInfo);

        // Assert
        Assert.NotNull(convertedJsonContent);

        AIContent convertedContent = convertedJsonContent.ToAIContent();

        DataContent convertedDataContent = Assert.IsType<DataContent>(convertedContent);

        Assert.Equal(dataContent.Uri, convertedDataContent.Uri);
        Assert.Equal(dataContent.MediaType, convertedDataContent.MediaType);
    }

    [Fact]
    public void HostedFileContentSerializationDeserialization()
    {
        // Arrange
        HostedFileContent hostedFileContent = new("file-123");

        DurableAgentStateContent durableContent = DurableAgentStateContent.FromAIContent(hostedFileContent);

        // Act
        string jsonContent = JsonSerializer.Serialize(durableContent, s_stateContentTypeInfo);

        DurableAgentStateContent? convertedJsonContent =
            (DurableAgentStateContent?)JsonSerializer.Deserialize(jsonContent, s_stateContentTypeInfo);

        // Assert
        Assert.NotNull(convertedJsonContent);

        AIContent convertedContent = convertedJsonContent.ToAIContent();

        HostedFileContent convertedHostedFileContent = Assert.IsType<HostedFileContent>(convertedContent);

        Assert.Equal(hostedFileContent.FileId, convertedHostedFileContent.FileId);
    }

    [Fact]
    public void HostedVectorStoreContentSerializationDeserialization()
    {
        // Arrange
        HostedVectorStoreContent hostedVectorStoreContent = new("vs-123");

        DurableAgentStateContent durableContent = DurableAgentStateContent.FromAIContent(hostedVectorStoreContent);

        // Act
        string jsonContent = JsonSerializer.Serialize(durableContent, s_stateContentTypeInfo);

        DurableAgentStateContent? convertedJsonContent =
            (DurableAgentStateContent?)JsonSerializer.Deserialize(jsonContent, s_stateContentTypeInfo);

        // Assert
        Assert.NotNull(convertedJsonContent);

        AIContent convertedContent = convertedJsonContent.ToAIContent();

        HostedVectorStoreContent convertedHostedVectorStoreContent = Assert.IsType<HostedVectorStoreContent>(convertedContent);

        Assert.Equal(hostedVectorStoreContent.VectorStoreId, convertedHostedVectorStoreContent.VectorStoreId);
    }

    [Fact]
    public void TextReasoningContentSerializationDeserialization()
    {
        // Arrange
        TextReasoningContent textReasoningContent = new("Reasoning chain...");

        DurableAgentStateContent durableContent = DurableAgentStateContent.FromAIContent(textReasoningContent);

        // Act
        string jsonContent = JsonSerializer.Serialize(durableContent, s_stateContentTypeInfo);

        DurableAgentStateContent? convertedJsonContent =
            (DurableAgentStateContent?)JsonSerializer.Deserialize(jsonContent, s_stateContentTypeInfo);

        // Assert
        Assert.NotNull(convertedJsonContent);

        AIContent convertedContent = convertedJsonContent.ToAIContent();

        TextReasoningContent convertedTextReasoningContent = Assert.IsType<TextReasoningContent>(convertedContent);

        Assert.Equal(textReasoningContent.Text, convertedTextReasoningContent.Text);
    }

    [Fact]
    public void UriContentSerializationDeserialization()
    {
        // Arrange
        UriContent uriContent = new(new Uri("https://example.com"), "text/html");

        DurableAgentStateContent durableContent = DurableAgentStateContent.FromAIContent(uriContent);

        // Act
        string jsonContent = JsonSerializer.Serialize(durableContent, s_stateContentTypeInfo);

        DurableAgentStateContent? convertedJsonContent =
            (DurableAgentStateContent?)JsonSerializer.Deserialize(jsonContent, s_stateContentTypeInfo);

        // Assert
        Assert.NotNull(convertedJsonContent);

        AIContent convertedContent = convertedJsonContent.ToAIContent();

        UriContent convertedUriContent = Assert.IsType<UriContent>(convertedContent);

        Assert.Equal(uriContent.Uri, convertedUriContent.Uri);
        Assert.Equal(uriContent.MediaType, convertedUriContent.MediaType);
    }

    [Fact]
    public void UsageContentSerializationDeserialization()
    {
        // Arrange
        UsageDetails usageDetails = new()
        {
            InputTokenCount = 10,
            OutputTokenCount = 5,
            TotalTokenCount = 15
        };

        UsageContent usageContent = new(usageDetails);

        DurableAgentStateContent durableContent = DurableAgentStateContent.FromAIContent(usageContent);

        // Act
        string jsonContent = JsonSerializer.Serialize(durableContent, s_stateContentTypeInfo);

        DurableAgentStateContent? convertedJsonContent =
            (DurableAgentStateContent?)JsonSerializer.Deserialize(jsonContent, s_stateContentTypeInfo);

        // Assert
        Assert.NotNull(convertedJsonContent);

        AIContent convertedContent = convertedJsonContent.ToAIContent();

        UsageContent convertedUsageContent = Assert.IsType<UsageContent>(convertedContent);

        Assert.NotNull(convertedUsageContent.Details);
        Assert.Equal(usageDetails.InputTokenCount, convertedUsageContent.Details.InputTokenCount);
        Assert.Equal(usageDetails.OutputTokenCount, convertedUsageContent.Details.OutputTokenCount);
        Assert.Equal(usageDetails.TotalTokenCount, convertedUsageContent.Details.TotalTokenCount);
    }

    [Fact]
    public void UnknownContentSerializationDeserialization()
    {
        // Arrange
        TextContent originalContent = new("Some unknown content");

        DurableAgentStateContent durableContent = DurableAgentStateUnknownContent.FromUnknownContent(originalContent);

        // Act
        string jsonContent = JsonSerializer.Serialize(durableContent, s_stateContentTypeInfo);

        DurableAgentStateContent? convertedJsonContent =
            (DurableAgentStateContent?)JsonSerializer.Deserialize(jsonContent, s_stateContentTypeInfo);

        // Assert
        Assert.NotNull(convertedJsonContent);

        AIContent convertedContent = convertedJsonContent.ToAIContent();

        TextContent convertedTextContent = Assert.IsType<TextContent>(convertedContent);

        Assert.Equal(originalContent.Text, convertedTextContent.Text);
    }
}
