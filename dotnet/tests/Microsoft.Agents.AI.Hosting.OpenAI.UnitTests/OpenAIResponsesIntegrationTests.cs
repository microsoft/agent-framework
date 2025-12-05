// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using OpenAI;
using OpenAI.Responses;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Integration tests that start a web server and use the OpenAI Responses SDK client to verify protocol compatibility.
/// These tests validate both streaming and non-streaming request scenarios.
/// </summary>
public sealed class OpenAIResponsesIntegrationTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _httpClient;

    public async ValueTask DisposeAsync()
    {
        this._httpClient?.Dispose();
        if (this._app != null)
        {
            await this._app.DisposeAsync();
        }
    }

    /// <summary>
    /// Verifies that streaming responses work correctly with the OpenAI SDK client.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_WithSimpleMessage_ReturnsStreamingUpdatesAsync()
    {
        // Arrange
        const string AgentName = "streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "One Two Three";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Count to 3");

        // Assert
        List<StreamingResponseUpdate> updates = [];
        StringBuilder contentBuilder = new();
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            updates.Add(update);
            if (update is StreamingResponseOutputTextDeltaUpdate textDelta)
            {
                contentBuilder.Append(textDelta.Delta);
            }
        }

        Assert.NotEmpty(updates);

        // Verify we got various streaming update types
        Assert.Contains(updates, u => u is StreamingResponseCreatedUpdate);
        Assert.Contains(updates, u => u is StreamingResponseCompletedUpdate);
        Assert.Contains(updates, u => u is StreamingResponseOutputTextDeltaUpdate);

        // Verify content was received
        string content = contentBuilder.ToString();
        Assert.Equal(ExpectedResponse, content);
    }

    /// <summary>
    /// Verifies that non-streaming responses work correctly with the OpenAI SDK client.
    /// </summary>
    [Fact]
    public async Task CreateResponse_WithSimpleMessage_ReturnsCompleteResponseAsync()
    {
        // Arrange
        const string AgentName = "non-streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Hello! How can I help you today?";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        OpenAIResponse response = await responseClient.CreateResponseAsync("Hello");

        // Assert
        Assert.NotNull(response);
        Assert.Equal(ResponseStatus.Completed, response.Status);
        Assert.NotNull(response.Id);

        // Verify content
        string content = response.GetOutputText();
        Assert.Equal(ExpectedResponse, content);
    }

    /// <summary>
    /// Verifies that streaming responses can handle multiple content chunks.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_WithMultipleChunks_StreamsAllContentAsync()
    {
        // Arrange
        const string AgentName = "multi-chunk-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "This is a test response with multiple words";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        List<StreamingResponseUpdate> updates = [];
        StringBuilder contentBuilder = new();
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            updates.Add(update);
            if (update is StreamingResponseOutputTextDeltaUpdate textDelta)
            {
                contentBuilder.Append(textDelta.Delta);
            }
        }

        // Verify all content was received
        string receivedContent = contentBuilder.ToString();
        Assert.Equal(ExpectedResponse, receivedContent);

        // Verify multiple content chunks were received
        List<StreamingResponseOutputTextDeltaUpdate> contentUpdates = updates.OfType<StreamingResponseOutputTextDeltaUpdate>().ToList();
        Assert.True(contentUpdates.Count > 1, "Expected multiple content chunks in streaming response");
    }

    /// <summary>
    /// Verifies that multiple agents can be accessed via the same server.
    /// </summary>
    [Fact]
    public async Task CreateResponse_WithMultipleAgents_EachAgentRespondsCorrectlyAsync()
    {
        // Arrange
        const string Agent1Name = "agent-one";
        const string Agent1Instructions = "You are agent one.";
        const string Agent1Response = "Response from agent one";

        const string Agent2Name = "agent-two";
        const string Agent2Instructions = "You are agent two.";
        const string Agent2Response = "Response from agent two";

        this._httpClient = await this.CreateTestServerWithMultipleAgentsAsync(
            (Agent1Name, Agent1Instructions, Agent1Response),
            (Agent2Name, Agent2Instructions, Agent2Response));

        OpenAIResponseClient responseClient1 = this.CreateResponseClient(Agent1Name);
        OpenAIResponseClient responseClient2 = this.CreateResponseClient(Agent2Name);

        // Act
        OpenAIResponse response1 = await responseClient1.CreateResponseAsync("Hello");
        OpenAIResponse response2 = await responseClient2.CreateResponseAsync("Hello");

        // Assert
        string content1 = response1.GetOutputText();
        string content2 = response2.GetOutputText();

        Assert.Equal(Agent1Response, content1);
        Assert.Equal(Agent2Response, content2);
        Assert.NotEqual(content1, content2);
    }

    /// <summary>
    /// Verifies that streaming and non-streaming work correctly for the same agent.
    /// </summary>
    [Fact]
    public async Task CreateResponse_SameAgentStreamingAndNonStreaming_BothWorkCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "dual-mode-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "This is the response";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act - Non-streaming
        OpenAIResponse nonStreamingResponse = await responseClient.CreateResponseAsync("Test");

        // Act - Streaming
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");
        StringBuilder streamingContent = new();
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            if (update is StreamingResponseOutputTextDeltaUpdate textDelta)
            {
                streamingContent.Append(textDelta.Delta);
            }
        }

        // Assert
        string nonStreamingContent = nonStreamingResponse.GetOutputText();
        Assert.Equal(ExpectedResponse, nonStreamingContent);
        Assert.Equal(ExpectedResponse, streamingContent.ToString());
    }

    /// <summary>
    /// Verifies that the response status is correctly set for completed responses.
    /// </summary>
    [Fact]
    public async Task CreateResponse_CompletedResponse_HasCorrectStatusAsync()
    {
        // Arrange
        const string AgentName = "status-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Complete";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        OpenAIResponse response = await responseClient.CreateResponseAsync("Test");

        // Assert
        Assert.Equal(ResponseStatus.Completed, response.Status);
        Assert.NotNull(response.Id);
        Assert.Equal(ExpectedResponse, response.GetOutputText());
    }

    /// <summary>
    /// Verifies that streaming responses contain the expected event sequence.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_VerifyEventSequence_ContainsExpectedEventsAsync()
    {
        // Arrange
        const string AgentName = "event-sequence-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Test response with multiple words";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        List<StreamingResponseUpdate> updates = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            updates.Add(update);
        }

        // Verify event sequence
        Assert.NotEmpty(updates);

        // First event should be created
        Assert.IsType<StreamingResponseCreatedUpdate>(updates[0]);

        // Last event should be completed
        StreamingResponseUpdate lastUpdate = updates[^1];
        Assert.IsType<StreamingResponseCompletedUpdate>(lastUpdate);

        // Should contain text delta events in between
        List<StreamingResponseUpdate> textDeltas = updates.Where(u => u is StreamingResponseOutputTextDeltaUpdate).ToList();
        Assert.NotEmpty(textDeltas);
    }

    /// <summary>
    /// Verifies that streaming responses properly handle empty responses.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_EmptyResponse_HandlesGracefullyAsync()
    {
        // Arrange
        const string AgentName = "empty-response-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        List<StreamingResponseUpdate> updates = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            updates.Add(update);
        }

        // Should still receive created and completed events
        Assert.NotEmpty(updates);
        Assert.Contains(updates, u => u is StreamingResponseCreatedUpdate);
        Assert.Contains(updates, u => u is StreamingResponseCompletedUpdate);
    }

    /// <summary>
    /// Verifies that non-streaming responses include proper metadata.
    /// </summary>
    [Fact]
    public async Task CreateResponse_IncludesMetadata_HasRequiredFieldsAsync()
    {
        // Arrange
        const string AgentName = "metadata-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Response with metadata";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        OpenAIResponse response = await responseClient.CreateResponseAsync("Test");

        // Assert
        Assert.NotNull(response.Id);
        Assert.NotNull(response.Model);
        Assert.NotEqual(default, response.CreatedAt);
        Assert.Equal(ResponseStatus.Completed, response.Status);
    }

    /// <summary>
    /// Verifies that streaming responses handle very long text correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_LongText_StreamsAllContentAsync()
    {
        // Arrange
        const string AgentName = "long-text-agent";
        const string Instructions = "You are a helpful assistant.";
        string expectedResponse = string.Join(" ", Enumerable.Range(1, 100).Select(i => $"Word{i}"));

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, expectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Generate long text");

        // Assert
        StringBuilder contentBuilder = new();
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            if (update is StreamingResponseOutputTextDeltaUpdate textDelta)
            {
                contentBuilder.Append(textDelta.Delta);
            }
        }

        string receivedContent = contentBuilder.ToString();
        Assert.Equal(expectedResponse, receivedContent);
    }

    /// <summary>
    /// Verifies that streaming responses properly track output indices.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_OutputIndices_AreConsistentAsync()
    {
        // Arrange
        const string AgentName = "output-index-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Test output index";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        List<int> outputIndices = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            if (update is StreamingResponseOutputItemAddedUpdate itemAdded)
            {
                outputIndices.Add(itemAdded.OutputIndex);
            }
            if (update is StreamingResponseOutputTextDeltaUpdate textDelta)
            {
                outputIndices.Add(textDelta.OutputIndex);
            }
        }

        // All output indices should be the same (first output)
        Assert.NotEmpty(outputIndices);
        Assert.All(outputIndices, index => Assert.Equal(0, index));
    }

    /// <summary>
    /// Verifies that streaming responses handle single-word responses correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_SingleWord_StreamsCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "single-word-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Hello";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        StringBuilder contentBuilder = new();
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            if (update is StreamingResponseOutputTextDeltaUpdate textDelta)
            {
                contentBuilder.Append(textDelta.Delta);
            }
        }

        Assert.Equal(ExpectedResponse, contentBuilder.ToString());
    }

    /// <summary>
    /// Verifies that streaming responses preserve special characters and formatting.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_SpecialCharacters_PreservesFormattingAsync()
    {
        // Arrange
        const string AgentName = "special-chars-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Hello! How are you? I'm fine. 100% great!";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        StringBuilder contentBuilder = new();
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            if (update is StreamingResponseOutputTextDeltaUpdate textDelta)
            {
                contentBuilder.Append(textDelta.Delta);
            }
        }

        Assert.Equal(ExpectedResponse, contentBuilder.ToString());
    }

    /// <summary>
    /// Verifies that non-streaming responses handle special characters correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponse_SpecialCharacters_PreservesContentAsync()
    {
        // Arrange
        const string AgentName = "special-chars-nonstreaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Symbols: @#$%^&*() Quotes: \"Hello\" 'World' Unicode: 你好 🌍";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        OpenAIResponse response = await responseClient.CreateResponseAsync("Test");

        // Assert
        string content = response.GetOutputText();
        Assert.Equal(ExpectedResponse, content);
    }

    /// <summary>
    /// Verifies that streaming responses include item IDs consistently.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_ItemIds_AreConsistentAsync()
    {
        // Arrange
        const string AgentName = "item-id-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Testing item IDs";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        List<string> itemIds = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            if (update is StreamingResponseOutputItemAddedUpdate itemAdded)
            {
                itemIds.Add(itemAdded.Item.Id);
            }
            if (update is StreamingResponseOutputTextDeltaUpdate textDelta && !string.IsNullOrEmpty(textDelta.ItemId))
            {
                itemIds.Add(textDelta.ItemId);
            }
        }

        // All item IDs should be the same within a single response
        Assert.NotEmpty(itemIds);
        Assert.All(itemIds, id => Assert.Equal(itemIds[0], id));
    }

    /// <summary>
    /// Verifies that multiple sequential non-streaming requests work correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponse_MultipleSequentialRequests_AllSucceedAsync()
    {
        // Arrange
        const string AgentName = "sequential-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Response";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act & Assert - Make 5 sequential requests
        for (int i = 0; i < 5; i++)
        {
            OpenAIResponse response = await responseClient.CreateResponseAsync($"Request {i}");
            Assert.NotNull(response);
            Assert.Equal(ResponseStatus.Completed, response.Status);
            Assert.Equal(ExpectedResponse, response.GetOutputText());
        }
    }

    /// <summary>
    /// Verifies that multiple sequential streaming requests work correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_MultipleSequentialRequests_AllStreamCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "sequential-streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Streaming response";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act & Assert - Make 3 sequential streaming requests
        for (int i = 0; i < 3; i++)
        {
            AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync($"Request {i}");
            StringBuilder contentBuilder = new();

            await foreach (StreamingResponseUpdate update in streamingResult)
            {
                if (update is StreamingResponseOutputTextDeltaUpdate textDelta)
                {
                    contentBuilder.Append(textDelta.Delta);
                }
            }

            Assert.Equal(ExpectedResponse, contentBuilder.ToString());
        }
    }

    /// <summary>
    /// Verifies that response IDs are unique across multiple requests.
    /// </summary>
    [Fact]
    public async Task CreateResponse_MultipleRequests_GenerateUniqueIdsAsync()
    {
        // Arrange
        const string AgentName = "unique-id-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Response";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        List<string> responseIds = [];
        for (int i = 0; i < 10; i++)
        {
            OpenAIResponse response = await responseClient.CreateResponseAsync($"Request {i}");
            responseIds.Add(response.Id);
        }

        // Assert
        Assert.Equal(10, responseIds.Count);
        Assert.Equal(responseIds.Count, responseIds.Distinct().Count()); // All IDs should be unique
    }

    /// <summary>
    /// Verifies that streaming responses track sequence numbers correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_SequenceNumbers_AreMonotonicallyIncreasingAsync()
    {
        // Arrange
        const string AgentName = "sequence-number-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Test sequence numbers with multiple words";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        List<int> sequenceNumbers = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            sequenceNumbers.Add(update.SequenceNumber);
        }

        // Verify sequence numbers are monotonically increasing starting from 0
        Assert.NotEmpty(sequenceNumbers);
        Assert.Equal(0, sequenceNumbers[0]);
        for (int i = 1; i < sequenceNumbers.Count; i++)
        {
            Assert.True(sequenceNumbers[i] > sequenceNumbers[i - 1], $"Sequence number {sequenceNumbers[i]} should be greater than {sequenceNumbers[i - 1]}");
        }
    }

    /// <summary>
    /// Verifies that non-streaming responses have correct model information.
    /// </summary>
    [Fact]
    public async Task CreateResponse_ModelInformation_IsCorrectAsync()
    {
        // Arrange
        const string AgentName = "model-info-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Test model info";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        OpenAIResponse response = await responseClient.CreateResponseAsync("Test");

        // Assert
        Assert.NotNull(response.Model);
        Assert.NotEmpty(response.Model);
    }

    /// <summary>
    /// Verifies that streaming responses properly handle responses with punctuation.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_Punctuation_PreservesContentAsync()
    {
        // Arrange
        const string AgentName = "punctuation-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Hello, world! How are you today? I'm doing well.";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        StringBuilder contentBuilder = new();
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            if (update is StreamingResponseOutputTextDeltaUpdate textDelta)
            {
                contentBuilder.Append(textDelta.Delta);
            }
        }

        Assert.Equal(ExpectedResponse, contentBuilder.ToString());
    }

    /// <summary>
    /// Verifies that non-streaming responses work with very short input.
    /// </summary>
    [Fact]
    public async Task CreateResponse_ShortInput_ReturnsValidResponseAsync()
    {
        // Arrange
        const string AgentName = "short-input-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "OK";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        OpenAIResponse response = await responseClient.CreateResponseAsync("Hi");

        // Assert
        Assert.NotNull(response);
        Assert.Equal(ResponseStatus.Completed, response.Status);
        Assert.Equal(ExpectedResponse, response.GetOutputText());
    }

    /// <summary>
    /// Verifies that streaming responses contain content index information.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_ContentIndices_AreConsistentAsync()
    {
        // Arrange
        const string AgentName = "content-index-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Test content indices";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        List<int> contentIndices = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            if (update is StreamingResponseOutputTextDeltaUpdate textDelta)
            {
                contentIndices.Add(textDelta.ContentIndex);
            }
        }

        // All content indices should be the same for a single text response
        Assert.NotEmpty(contentIndices);
        Assert.All(contentIndices, index => Assert.Equal(0, index));
    }

    /// <summary>
    /// Verifies that non-streaming responses handle newlines correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponse_Newlines_PreservesFormattingAsync()
    {
        // Arrange
        const string AgentName = "newline-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Line 1\nLine 2\nLine 3";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        OpenAIResponse response = await responseClient.CreateResponseAsync("Test");

        // Assert
        string content = response.GetOutputText();
        Assert.Equal(ExpectedResponse, content);
        Assert.Contains("\n", content);
    }

    /// <summary>
    /// Verifies that streaming responses handle newlines correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_Newlines_PreservesFormattingAsync()
    {
        // Arrange
        const string AgentName = "newline-streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "First line\nSecond line\nThird line";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        StringBuilder contentBuilder = new();
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            if (update is StreamingResponseOutputTextDeltaUpdate textDelta)
            {
                contentBuilder.Append(textDelta.Delta);
            }
        }

        string content = contentBuilder.ToString();
        Assert.Equal(ExpectedResponse, content);
        Assert.Contains("\n", content);
    }

    /// <summary>
    /// Verifies that responses with image content are properly handled in non-streaming mode.
    /// </summary>
    [Fact]
    public async Task CreateResponse_ImageContent_ReturnsCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "image-content-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ImageUrl = "https://example.com/test-image.png";

        this._httpClient = await this.CreateTestServerWithCustomClientAsync(
            agentName: AgentName,
            instructions: Instructions,
            chatClient: new TestHelpers.ImageContentMockChatClient(ImageUrl));

        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        OpenAIResponse response = await responseClient.CreateResponseAsync("Show me an image");

        // Assert
        Assert.NotNull(response);
        Assert.Equal(ResponseStatus.Completed, response.Status);
        Assert.NotNull(response.Id);
    }

    /// <summary>
    /// Verifies that responses with image content stream correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_ImageContent_StreamsCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "image-streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ImageUrl = "https://example.com/test-image.png";

        this._httpClient = await this.CreateTestServerWithCustomClientAsync(
            agentName: AgentName,
            instructions: Instructions,
            chatClient: new TestHelpers.ImageContentMockChatClient(ImageUrl));

        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Show me an image");

        // Assert
        List<StreamingResponseUpdate> updates = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            updates.Add(update);
        }

        Assert.NotEmpty(updates);
        Assert.Contains(updates, u => u is StreamingResponseCreatedUpdate);
        Assert.Contains(updates, u => u is StreamingResponseCompletedUpdate);
    }

    /// <summary>
    /// Verifies that responses with audio content are properly handled.
    /// </summary>
    [Fact]
    public async Task CreateResponse_AudioContent_ReturnsCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "audio-content-agent";
        const string Instructions = "You are a helpful assistant.";
        const string AudioData = "base64_audio_data_here";
        const string Transcript = "This is the audio transcript";

        this._httpClient = await this.CreateTestServerWithCustomClientAsync(
            agentName: AgentName,
            instructions: Instructions,
            chatClient: new TestHelpers.AudioContentMockChatClient(AudioData, Transcript));

        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        OpenAIResponse response = await responseClient.CreateResponseAsync("Generate audio");

        // Assert
        Assert.NotNull(response);
        Assert.Equal(ResponseStatus.Completed, response.Status);
        Assert.NotNull(response.Id);
    }

    /// <summary>
    /// Verifies that responses with audio content stream correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_AudioContent_StreamsCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "audio-streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string AudioData = "base64_audio_data";
        const string Transcript = "Audio transcript";

        this._httpClient = await this.CreateTestServerWithCustomClientAsync(
            agentName: AgentName,
            instructions: Instructions,
            chatClient: new TestHelpers.AudioContentMockChatClient(AudioData, Transcript));

        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Generate audio");

        // Assert
        List<StreamingResponseUpdate> updates = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            updates.Add(update);
        }

        Assert.NotEmpty(updates);
        Assert.Contains(updates, u => u is StreamingResponseCreatedUpdate);
        Assert.Contains(updates, u => u is StreamingResponseCompletedUpdate);
    }

    /// <summary>
    /// Verifies that responses with function calls are properly handled.
    /// </summary>
    [Fact]
    public async Task CreateResponse_FunctionCall_ReturnsCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "function-call-agent";
        const string Instructions = "You are a helpful assistant.";
        const string FunctionName = "get_weather";
        const string Arguments = "{\"location\":\"Seattle\"}";

        this._httpClient = await this.CreateTestServerWithCustomClientAsync(
            agentName: AgentName,
            instructions: Instructions,
            chatClient: new TestHelpers.FunctionCallMockChatClient(FunctionName, Arguments));

        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        OpenAIResponse response = await responseClient.CreateResponseAsync("What's the weather?");

        // Assert
        Assert.NotNull(response);
        Assert.NotNull(response.Id);
    }

    /// <summary>
    /// Verifies that responses with function calls stream correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_FunctionCall_StreamsCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "function-call-streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string FunctionName = "calculate";
        const string Arguments = "{\"expression\":\"2+2\"}";

        this._httpClient = await this.CreateTestServerWithCustomClientAsync(
            agentName: AgentName,
            instructions: Instructions,
            chatClient: new TestHelpers.FunctionCallMockChatClient(FunctionName, Arguments));

        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Calculate 2+2");

        // Assert
        List<StreamingResponseUpdate> updates = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            updates.Add(update);
        }

        Assert.NotEmpty(updates);
        Assert.Contains(updates, u => u is StreamingResponseCreatedUpdate);
    }

    /// <summary>
    /// Verifies that responses with mixed content types are properly handled.
    /// </summary>
    [Fact]
    public async Task CreateResponse_MixedContent_ReturnsCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "mixed-content-agent";
        const string Instructions = "You are a helpful assistant.";

        this._httpClient = await this.CreateTestServerWithCustomClientAsync(
            agentName: AgentName,
            instructions: Instructions,
            chatClient: new TestHelpers.MixedContentMockChatClient());

        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        OpenAIResponse response = await responseClient.CreateResponseAsync("Show me various content");

        // Assert
        Assert.NotNull(response);
        Assert.Equal(ResponseStatus.Completed, response.Status);
        Assert.NotNull(response.Id);
    }

    /// <summary>
    /// Verifies that responses with mixed content types stream correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_MixedContent_StreamsCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "mixed-streaming-agent";
        const string Instructions = "You are a helpful assistant.";

        this._httpClient = await this.CreateTestServerWithCustomClientAsync(
            agentName: AgentName,
            instructions: Instructions,
            chatClient: new TestHelpers.MixedContentMockChatClient());

        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Show me various content");

        // Assert
        List<StreamingResponseUpdate> updates = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            updates.Add(update);
        }

        Assert.NotEmpty(updates);
        Assert.Contains(updates, u => u is StreamingResponseCreatedUpdate);
        Assert.Contains(updates, u => u is StreamingResponseCompletedUpdate);

        // Should have multiple output item added events due to different content types
        List<StreamingResponseUpdate> itemAddedUpdates = updates.Where(u => u is StreamingResponseOutputItemAddedUpdate).ToList();
        Assert.NotEmpty(itemAddedUpdates);
    }

    /// <summary>
    /// Verifies that streaming text content includes proper done events.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_TextDone_IncludesDoneEventAsync()
    {
        // Arrange
        const string AgentName = "text-done-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Complete text response";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        List<StreamingResponseUpdate> updates = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            updates.Add(update);
        }

        // Should contain completed event (text done is represented by completed status)
        Assert.Contains(updates, u => u is StreamingResponseCompletedUpdate);
    }

    /// <summary>
    /// Verifies that content part added events are included in streaming responses.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_ContentPartAdded_IncludesEventAsync()
    {
        // Arrange
        const string AgentName = "content-part-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Response with content parts";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        OpenAIResponseClient responseClient = this.CreateResponseClient(AgentName);

        // Act
        AsyncCollectionResult<StreamingResponseUpdate> streamingResult = responseClient.CreateResponseStreamingAsync("Test");

        // Assert
        List<StreamingResponseUpdate> updates = [];
        await foreach (StreamingResponseUpdate update in streamingResult)
        {
            updates.Add(update);
        }

        // Should contain content part added event
        Assert.Contains(updates, u => u is StreamingResponseContentPartAddedUpdate);
    }

    /// <summary>
    /// Verifies that when a client provides a conversation ID, the underlying IChatClient
    /// does NOT receive that conversation ID via ChatOptions.ConversationId.
    /// This ensures that the host's conversation management is separate from the IChatClient's
    /// conversation handling (if any).
    /// </summary>
    [Fact]
    public async Task CreateResponse_WithConversationId_DoesNotForwardConversationIdToIChatClientAsync()
    {
        // Arrange
        const string AgentName = "conversation-id-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Response";

        this._httpClient = await this.CreateTestServerWithConversationsAsync(AgentName, Instructions, ExpectedResponse);
        var mockChatClient = this.ResolveMockChatClient();

        // First, create a conversation
        var createConversationRequest = new { metadata = new { agent_id = AgentName } };
        string createConvJson = System.Text.Json.JsonSerializer.Serialize(createConversationRequest);
        using StringContent createConvContent = new(createConvJson, Encoding.UTF8, "application/json");
        HttpResponseMessage createConvResponse = await this._httpClient.PostAsync(
            new Uri("/v1/conversations", UriKind.Relative),
            createConvContent);
        Assert.True(createConvResponse.IsSuccessStatusCode, $"Create conversation failed: {createConvResponse.StatusCode}");

        string convResponseJson = await createConvResponse.Content.ReadAsStringAsync();
        using var convDoc = System.Text.Json.JsonDocument.Parse(convResponseJson);
        string conversationId = convDoc.RootElement.GetProperty("id").GetString()!;

        // Act - Send request with conversation ID using raw HTTP
        // (OpenAI SDK doesn't expose ConversationId directly on ResponseCreationOptions)
        var requestBody = new
        {
            input = "Test",
            agent = new { name = AgentName },
            conversation = conversationId,
            stream = false
        };
        string requestJson = System.Text.Json.JsonSerializer.Serialize(requestBody);
        using StringContent content = new(requestJson, Encoding.UTF8, "application/json");
        HttpResponseMessage httpResponse = await this._httpClient.PostAsync(
            new Uri($"/{AgentName}/v1/responses", UriKind.Relative),
            content);

        // Assert - Response is successful
        Assert.True(httpResponse.IsSuccessStatusCode, $"Response status: {httpResponse.StatusCode}");

        // Assert - The IChatClient should have received ChatOptions, but without the ConversationId set
        Assert.NotNull(mockChatClient.LastChatOptions);
        Assert.Null(mockChatClient.LastChatOptions.ConversationId);
    }

    /// <summary>
    /// Verifies that when a client provides a conversation ID in streaming mode, the underlying
    /// IChatClient does NOT receive that conversation ID via ChatOptions.ConversationId.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_WithConversationId_DoesNotForwardConversationIdToIChatClientAsync()
    {
        // Arrange
        const string AgentName = "conversation-streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Streaming response";

        this._httpClient = await this.CreateTestServerWithConversationsAsync(AgentName, Instructions, ExpectedResponse);
        var mockChatClient = this.ResolveMockChatClient();

        // First, create a conversation
        var createConversationRequest = new { metadata = new { agent_id = AgentName } };
        string createConvJson = System.Text.Json.JsonSerializer.Serialize(createConversationRequest);
        using StringContent createConvContent = new(createConvJson, Encoding.UTF8, "application/json");
        HttpResponseMessage createConvResponse = await this._httpClient.PostAsync(
            new Uri("/v1/conversations", UriKind.Relative),
            createConvContent);
        Assert.True(createConvResponse.IsSuccessStatusCode, $"Create conversation failed: {createConvResponse.StatusCode}");

        string convResponseJson = await createConvResponse.Content.ReadAsStringAsync();
        using var convDoc = System.Text.Json.JsonDocument.Parse(convResponseJson);
        string conversationId = convDoc.RootElement.GetProperty("id").GetString()!;

        // Act - Send streaming request with conversation ID using raw HTTP
        var requestBody = new
        {
            input = "Test",
            agent = new { name = AgentName },
            conversation = conversationId,
            stream = true
        };
        string requestJson = System.Text.Json.JsonSerializer.Serialize(requestBody);
        using StringContent content = new(requestJson, Encoding.UTF8, "application/json");
        HttpResponseMessage httpResponse = await this._httpClient.PostAsync(
            new Uri($"/{AgentName}/v1/responses", UriKind.Relative),
            content);

        // Assert - Response is successful and is SSE
        Assert.True(httpResponse.IsSuccessStatusCode, $"Response status: {httpResponse.StatusCode}");
        Assert.Equal("text/event-stream", httpResponse.Content.Headers.ContentType?.MediaType);

        // Consume the SSE stream to complete the request
        string sseContent = await httpResponse.Content.ReadAsStringAsync();

        // Verify streaming completed successfully by checking for response.completed event
        Assert.Contains("response.completed", sseContent);

        // Assert - The IChatClient should have received ChatOptions, but without the ConversationId set
        Assert.NotNull(mockChatClient.LastChatOptions);
        Assert.Null(mockChatClient.LastChatOptions.ConversationId);
    }

    private OpenAIResponseClient CreateResponseClient(string agentName)
    {
        return new OpenAIResponseClient(
            model: "test-model",
            credential: new ApiKeyCredential("test-api-key"),
            options: new OpenAIClientOptions
            {
                Endpoint = new Uri(this._httpClient!.BaseAddress!, $"/{agentName}/v1/"),
                Transport = new HttpClientPipelineTransport(this._httpClient)
            });
    }

    private TestHelpers.SimpleMockChatClient ResolveMockChatClient()
    {
        ArgumentNullException.ThrowIfNull(this._app, nameof(this._app));

        var chatClient = this._app.Services.GetRequiredKeyedService<IChatClient>("chat-client");
        if (chatClient is not TestHelpers.SimpleMockChatClient mockChatClient)
        {
            throw new InvalidOperationException("Mock chat client not found or of incorrect type.");
        }

        return mockChatClient;
    }

    private async Task<HttpClient> CreateTestServerAsync(string agentName, string instructions, string responseText = "Test response")
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient(responseText);
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddOpenAIResponses();
        builder.AddAIAgent(agentName, instructions, chatClientServiceKey: "chat-client");

        this._app = builder.Build();
        AIAgent agent = this._app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        this._app.MapOpenAIResponses(agent);

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        return testServer.CreateClient();
    }

    private async Task<HttpClient> CreateTestServerWithConversationsAsync(string agentName, string instructions, string responseText = "Test response")
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient(responseText);
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddOpenAIResponses();
        builder.AddOpenAIConversations();
        builder.AddAIAgent(agentName, instructions, chatClientServiceKey: "chat-client");

        this._app = builder.Build();
        AIAgent agent = this._app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        this._app.MapOpenAIResponses(agent);
        this._app.MapOpenAIConversations();

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        return testServer.CreateClient();
    }

    private async Task<HttpClient> CreateTestServerWithCustomClientAsync(string agentName, string instructions, IChatClient chatClient)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        builder.Services.AddKeyedSingleton($"chat-client-{agentName}", chatClient);
        builder.AddAIAgent(agentName, instructions, chatClientServiceKey: $"chat-client-{agentName}");
        builder.AddOpenAIResponses();

        this._app = builder.Build();
        AIAgent agent = this._app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        this._app.MapOpenAIResponses(agent);

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        return testServer.CreateClient();
    }

    private async Task<HttpClient> CreateTestServerWithMultipleAgentsAsync(
        params (string Name, string Instructions, string ResponseText)[] agents)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        foreach ((string name, string instructions, string responseText) in agents)
        {
            IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient(responseText);
            builder.Services.AddKeyedSingleton($"chat-client-{name}", mockChatClient);
            builder.AddAIAgent(name, instructions, chatClientServiceKey: $"chat-client-{name}");
        }

        builder.AddOpenAIResponses();

        this._app = builder.Build();

        foreach ((string name, string _, string _) in agents)
        {
            AIAgent agent = this._app.Services.GetRequiredKeyedService<AIAgent>(name);
            this._app.MapOpenAIResponses(agent);
        }

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        return testServer.CreateClient();
    }
}
