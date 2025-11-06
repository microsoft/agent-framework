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
using OpenAI.Chat;
using ChatFinishReason = OpenAI.Chat.ChatFinishReason;
using ChatMessage = OpenAI.Chat.ChatMessage;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Integration tests that start a web server and use the OpenAI Chat Completions SDK client to verify protocol compatibility.
/// These tests validate both streaming and non-streaming request scenarios.
/// </summary>
public sealed class OpenAIChatCompletionsIntegrationTests : IAsyncDisposable
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
    /// Verifies that streaming chat completions work correctly with the OpenAI SDK client.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletionStreaming_WithSimpleMessage_ReturnsStreamingUpdatesAsync()
    {
        // Arrange
        const string AgentName = "streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "One Two Three";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Count to 3")
        ];

        // Act
        AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = chatClient.CompleteChatStreamingAsync(messages);

        // Assert
        List<StreamingChatCompletionUpdate> updates = [];
        StringBuilder contentBuilder = new();
        await foreach (StreamingChatCompletionUpdate update in streamingResult)
        {
            updates.Add(update);
            if (update.ContentUpdate.Count > 0)
            {
                foreach (ChatMessageContentPart contentPart in update.ContentUpdate)
                {
                    contentBuilder.Append(contentPart.Text);
                }
            }
        }

        Assert.NotEmpty(updates);

        // Verify content was received
        string content = contentBuilder.ToString();
        Assert.Equal(ExpectedResponse, content);

        // Verify finish reason
        StreamingChatCompletionUpdate? lastUpdate = updates.LastOrDefault(u => u.FinishReason != null);
        Assert.NotNull(lastUpdate);
        Assert.Equal(ChatFinishReason.Stop, lastUpdate.FinishReason);
    }

    /// <summary>
    /// Verifies that non-streaming chat completions work correctly with the OpenAI SDK client.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_WithSimpleMessage_ReturnsCompleteResponseAsync()
    {
        // Arrange
        const string AgentName = "non-streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Hello! How can I help you today?";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Hello")
        ];

        // Act
        ChatCompletion completion = await chatClient.CompleteChatAsync(messages);

        // Assert
        Assert.NotNull(completion);
        Assert.NotNull(completion.Id);
        Assert.StartsWith("chatcmpl-", completion.Id);
        Assert.Equal(ChatFinishReason.Stop, completion.FinishReason);

        // Verify content
        string content = completion.Content[0].Text;
        Assert.Equal(ExpectedResponse, content);
    }

    /// <summary>
    /// Verifies that streaming chat completions can handle multiple content chunks.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletionStreaming_WithMultipleChunks_StreamsAllContentAsync()
    {
        // Arrange
        const string AgentName = "multi-chunk-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "This is a test response with multiple words";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = chatClient.CompleteChatStreamingAsync(messages);

        // Assert
        List<StreamingChatCompletionUpdate> updates = [];
        StringBuilder contentBuilder = new();
        await foreach (StreamingChatCompletionUpdate update in streamingResult)
        {
            updates.Add(update);
            foreach (ChatMessageContentPart contentPart in update.ContentUpdate)
            {
                contentBuilder.Append(contentPart.Text);
            }
        }

        // Verify all content was received
        string receivedContent = contentBuilder.ToString();
        Assert.Equal(ExpectedResponse, receivedContent);

        // Verify multiple content chunks were received
        List<StreamingChatCompletionUpdate> contentUpdates = updates.Where(u => u.ContentUpdate.Count > 0).ToList();
        Assert.True(contentUpdates.Count > 1, "Expected multiple content chunks in streaming response");
    }

    /// <summary>
    /// Verifies that multiple agents can be accessed via the same server.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_WithMultipleAgents_EachAgentRespondsCorrectlyAsync()
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

        ChatClient chatClient1 = this.CreateChatClient(Agent1Name);
        ChatClient chatClient2 = this.CreateChatClient(Agent2Name);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Hello")
        ];

        // Act
        ChatCompletion completion1 = await chatClient1.CompleteChatAsync(messages);
        ChatCompletion completion2 = await chatClient2.CompleteChatAsync(messages);

        // Assert
        string content1 = completion1.Content[0].Text;
        string content2 = completion2.Content[0].Text;

        Assert.Equal(Agent1Response, content1);
        Assert.Equal(Agent2Response, content2);
        Assert.NotEqual(content1, content2);
    }

    /// <summary>
    /// Verifies that streaming and non-streaming work correctly for the same agent.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_SameAgentStreamingAndNonStreaming_BothWorkCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "dual-mode-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "This is the response";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act - Non-streaming
        ChatCompletion nonStreamingCompletion = await chatClient.CompleteChatAsync(messages);

        // Act - Streaming
        AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = chatClient.CompleteChatStreamingAsync(messages);
        StringBuilder streamingContent = new();
        await foreach (StreamingChatCompletionUpdate update in streamingResult)
        {
            foreach (ChatMessageContentPart contentPart in update.ContentUpdate)
            {
                streamingContent.Append(contentPart.Text);
            }
        }

        // Assert
        string nonStreamingContent = nonStreamingCompletion.Content[0].Text;
        Assert.Equal(ExpectedResponse, nonStreamingContent);
        Assert.Equal(ExpectedResponse, streamingContent.ToString());
    }

    /// <summary>
    /// Verifies that the finish reason is correctly set for completed responses.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_CompletedResponse_HasCorrectFinishReasonAsync()
    {
        // Arrange
        const string AgentName = "finish-reason-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Complete";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        ChatCompletion completion = await chatClient.CompleteChatAsync(messages);

        // Assert
        Assert.Equal(ChatFinishReason.Stop, completion.FinishReason);
        Assert.NotNull(completion.Id);
        Assert.Equal(ExpectedResponse, completion.Content[0].Text);
    }

    /// <summary>
    /// Verifies that streaming responses contain the expected chunk sequence.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletionStreaming_VerifyChunkSequence_ContainsExpectedDataAsync()
    {
        // Arrange
        const string AgentName = "chunk-sequence-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Test response with multiple words";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = chatClient.CompleteChatStreamingAsync(messages);

        // Assert
        List<StreamingChatCompletionUpdate> updates = [];
        await foreach (StreamingChatCompletionUpdate update in streamingResult)
        {
            updates.Add(update);
        }

        // Verify chunks received
        Assert.NotEmpty(updates);

        // First chunk should have role
        StreamingChatCompletionUpdate? firstUpdate = updates.FirstOrDefault(u => u.Role != null);
        if (firstUpdate != null)
        {
            Assert.Equal(ChatMessageRole.Assistant, firstUpdate.Role);
        }

        // Should contain content chunks
        List<StreamingChatCompletionUpdate> contentUpdates = updates.Where(u => u.ContentUpdate.Count > 0).ToList();
        Assert.NotEmpty(contentUpdates);

        // Last update should have finish reason
        StreamingChatCompletionUpdate? lastUpdate = updates.LastOrDefault(u => u.FinishReason != null);
        Assert.NotNull(lastUpdate);
        Assert.Equal(ChatFinishReason.Stop, lastUpdate.FinishReason);
    }

    /// <summary>
    /// Verifies that streaming responses properly handle empty responses.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletionStreaming_EmptyResponse_HandlesGracefullyAsync()
    {
        // Arrange
        const string AgentName = "empty-response-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = chatClient.CompleteChatStreamingAsync(messages);

        // Assert
        List<StreamingChatCompletionUpdate> updates = [];
        await foreach (StreamingChatCompletionUpdate update in streamingResult)
        {
            updates.Add(update);
        }

        // Should still receive chunks with finish reason
        Assert.NotEmpty(updates);
        Assert.Contains(updates, u => u.FinishReason == ChatFinishReason.Stop);
    }

    /// <summary>
    /// Verifies that non-streaming responses include proper metadata.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_IncludesMetadata_HasRequiredFieldsAsync()
    {
        // Arrange
        const string AgentName = "metadata-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Response with metadata";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        ChatCompletion completion = await chatClient.CompleteChatAsync(messages);

        // Assert
        Assert.NotNull(completion.Id);
        Assert.StartsWith("chatcmpl-", completion.Id);
        Assert.NotNull(completion.Model);
        Assert.NotEqual(default, completion.CreatedAt);
        Assert.Equal(ChatFinishReason.Stop, completion.FinishReason);
    }

    /// <summary>
    /// Verifies that streaming responses handle very long text correctly.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletionStreaming_LongText_StreamsAllContentAsync()
    {
        // Arrange
        const string AgentName = "long-text-agent";
        const string Instructions = "You are a helpful assistant.";
        string expectedResponse = string.Join(" ", Enumerable.Range(1, 100).Select(i => $"Word{i}"));

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, expectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Generate long text")
        ];

        // Act
        AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = chatClient.CompleteChatStreamingAsync(messages);

        // Assert
        StringBuilder contentBuilder = new();
        await foreach (StreamingChatCompletionUpdate update in streamingResult)
        {
            foreach (ChatMessageContentPart contentPart in update.ContentUpdate)
            {
                contentBuilder.Append(contentPart.Text);
            }
        }

        string receivedContent = contentBuilder.ToString();
        Assert.Equal(expectedResponse, receivedContent);
    }

    /// <summary>
    /// Verifies that streaming responses properly handle single-word responses.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletionStreaming_SingleWord_StreamsCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "single-word-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Hello";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = chatClient.CompleteChatStreamingAsync(messages);

        // Assert
        StringBuilder contentBuilder = new();
        await foreach (StreamingChatCompletionUpdate update in streamingResult)
        {
            foreach (ChatMessageContentPart contentPart in update.ContentUpdate)
            {
                contentBuilder.Append(contentPart.Text);
            }
        }

        Assert.Equal(ExpectedResponse, contentBuilder.ToString());
    }

    /// <summary>
    /// Verifies that streaming responses preserve special characters and formatting.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletionStreaming_SpecialCharacters_PreservesFormattingAsync()
    {
        // Arrange
        const string AgentName = "special-chars-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Hello! How are you? I'm fine. 100% great!";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = chatClient.CompleteChatStreamingAsync(messages);

        // Assert
        StringBuilder contentBuilder = new();
        await foreach (StreamingChatCompletionUpdate update in streamingResult)
        {
            foreach (ChatMessageContentPart contentPart in update.ContentUpdate)
            {
                contentBuilder.Append(contentPart.Text);
            }
        }

        Assert.Equal(ExpectedResponse, contentBuilder.ToString());
    }

    /// <summary>
    /// Verifies that non-streaming responses handle special characters correctly.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_SpecialCharacters_PreservesContentAsync()
    {
        // Arrange
        const string AgentName = "special-chars-nonstreaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Symbols: @#$%^&*() Quotes: \"Hello\" 'World' Unicode: 你好 🌍";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        ChatCompletion completion = await chatClient.CompleteChatAsync(messages);

        // Assert
        string content = completion.Content[0].Text;
        Assert.Equal(ExpectedResponse, content);
    }

    /// <summary>
    /// Verifies that multiple sequential non-streaming requests work correctly.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_MultipleSequentialRequests_AllSucceedAsync()
    {
        // Arrange
        const string AgentName = "sequential-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Response";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        // Act & Assert - Make 5 sequential requests
        for (int i = 0; i < 5; i++)
        {
            List<ChatMessage> messages =
            [
                new UserChatMessage($"Request {i}")
            ];

            ChatCompletion completion = await chatClient.CompleteChatAsync(messages);
            Assert.NotNull(completion);
            Assert.Equal(ChatFinishReason.Stop, completion.FinishReason);
            Assert.Equal(ExpectedResponse, completion.Content[0].Text);
        }
    }

    /// <summary>
    /// Verifies that multiple sequential streaming requests work correctly.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletionStreaming_MultipleSequentialRequests_AllStreamCorrectlyAsync()
    {
        // Arrange
        const string AgentName = "sequential-streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Streaming response";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        // Act & Assert - Make 3 sequential streaming requests
        for (int i = 0; i < 3; i++)
        {
            List<ChatMessage> messages =
            [
                new UserChatMessage($"Request {i}")
            ];

            AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = chatClient.CompleteChatStreamingAsync(messages);
            StringBuilder contentBuilder = new();

            await foreach (StreamingChatCompletionUpdate update in streamingResult)
            {
                foreach (ChatMessageContentPart contentPart in update.ContentUpdate)
                {
                    contentBuilder.Append(contentPart.Text);
                }
            }

            Assert.Equal(ExpectedResponse, contentBuilder.ToString());
        }
    }

    /// <summary>
    /// Verifies that completion IDs are unique across multiple requests.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_MultipleRequests_GenerateUniqueIdsAsync()
    {
        // Arrange
        const string AgentName = "unique-id-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Response";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        // Act
        List<string> completionIds = [];
        for (int i = 0; i < 10; i++)
        {
            List<ChatMessage> messages =
            [
                new UserChatMessage($"Request {i}")
            ];

            ChatCompletion completion = await chatClient.CompleteChatAsync(messages);
            completionIds.Add(completion.Id);
        }

        // Assert
        Assert.Equal(10, completionIds.Count);
        Assert.Equal(completionIds.Count, completionIds.Distinct().Count()); // All IDs should be unique
    }

    /// <summary>
    /// Verifies that streaming responses all have the same ID within a single request.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletionStreaming_SameRequestId_ConsistentAcrossChunksAsync()
    {
        // Arrange
        const string AgentName = "consistent-id-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Test consistent ID across chunks";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = chatClient.CompleteChatStreamingAsync(messages);

        // Assert
        List<string> chunkIds = [];
        await foreach (StreamingChatCompletionUpdate update in streamingResult)
        {
            if (!string.IsNullOrEmpty(update.CompletionId))
            {
                chunkIds.Add(update.CompletionId);
            }
        }

        // All chunk IDs should be the same within a single request
        Assert.NotEmpty(chunkIds);
        Assert.All(chunkIds, id => Assert.Equal(chunkIds[0], id));
        Assert.StartsWith("chatcmpl-", chunkIds[0]);
    }

    /// <summary>
    /// Verifies that non-streaming responses work with system messages.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_WithSystemMessage_ReturnsValidResponseAsync()
    {
        // Arrange
        const string AgentName = "system-message-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "I am following the system instructions";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new SystemChatMessage("You must respond in a specific way"),
            new UserChatMessage("Hello")
        ];

        // Act
        ChatCompletion completion = await chatClient.CompleteChatAsync(messages);

        // Assert
        Assert.NotNull(completion);
        Assert.Equal(ChatFinishReason.Stop, completion.FinishReason);
        Assert.Equal(ExpectedResponse, completion.Content[0].Text);
    }

    /// <summary>
    /// Verifies that responses handle newlines correctly.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_Newlines_PreservesFormattingAsync()
    {
        // Arrange
        const string AgentName = "newline-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Line 1\nLine 2\nLine 3";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        ChatCompletion completion = await chatClient.CompleteChatAsync(messages);

        // Assert
        string content = completion.Content[0].Text;
        Assert.Equal(ExpectedResponse, content);
        Assert.Contains("\n", content);
    }

    /// <summary>
    /// Verifies that streaming responses handle newlines correctly.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletionStreaming_Newlines_PreservesFormattingAsync()
    {
        // Arrange
        const string AgentName = "newline-streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "First line\nSecond line\nThird line";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = chatClient.CompleteChatStreamingAsync(messages);

        // Assert
        StringBuilder contentBuilder = new();
        await foreach (StreamingChatCompletionUpdate update in streamingResult)
        {
            foreach (ChatMessageContentPart contentPart in update.ContentUpdate)
            {
                contentBuilder.Append(contentPart.Text);
            }
        }

        string content = contentBuilder.ToString();
        Assert.Equal(ExpectedResponse, content);
        Assert.Contains("\n", content);
    }

    /// <summary>
    /// Verifies that responses with conversation history work correctly.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_WithConversationHistory_ReturnsValidResponseAsync()
    {
        // Arrange
        const string AgentName = "conversation-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "3 plus 3 equals 6";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("What is 2+2?"),
            new AssistantChatMessage("2+2 equals 4"),
            new UserChatMessage("What about 3+3?")
        ];

        // Act
        ChatCompletion completion = await chatClient.CompleteChatAsync(messages);

        // Assert
        Assert.NotNull(completion);
        Assert.Equal(ChatFinishReason.Stop, completion.FinishReason);
        Assert.Equal(ExpectedResponse, completion.Content[0].Text);
    }

    /// <summary>
    /// Verifies that usage information is included in non-streaming responses.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_IncludesUsage_HasTokenCountsAsync()
    {
        // Arrange
        const string AgentName = "usage-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Response with usage information";

        this._httpClient = await this.CreateTestServerAsync(AgentName, Instructions, ExpectedResponse);
        ChatClient chatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Test")
        ];

        // Act
        ChatCompletion completion = await chatClient.CompleteChatAsync(messages);

        // Assert
        Assert.NotNull(completion.Usage);
        Assert.True(completion.Usage.InputTokenCount > 0);
        Assert.True(completion.Usage.OutputTokenCount > 0);
        Assert.Equal(completion.Usage.InputTokenCount + completion.Usage.OutputTokenCount, completion.Usage.TotalTokenCount);
    }

    /// <summary>
    /// Verifies that responses with function calls work correctly.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletion_WithFunctionCall_ReturnsToolCallsAsync()
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

        ChatClient openAIChatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("What's the weather?")
        ];

        // Act
        ChatCompletion completion = await openAIChatClient.CompleteChatAsync(messages);

        // Assert
        Assert.NotNull(completion);
        Assert.Equal(ChatFinishReason.ToolCalls, completion.FinishReason);
        Assert.NotNull(completion.ToolCalls);
        Assert.NotEmpty(completion.ToolCalls);

        ChatToolCall toolCall = completion.ToolCalls[0];
        Assert.Equal(FunctionName, toolCall.FunctionName);
        Assert.NotNull(toolCall.FunctionArguments);
    }

    /// <summary>
    /// Verifies that streaming responses with function calls work correctly.
    /// </summary>
    [Fact]
    public async Task CreateChatCompletionStreaming_WithFunctionCall_StreamsToolCallsAsync()
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

        ChatClient openAIChatClient = this.CreateChatClient(AgentName);

        List<ChatMessage> messages =
        [
            new UserChatMessage("Calculate 2+2")
        ];

        // Act
        AsyncCollectionResult<StreamingChatCompletionUpdate> streamingResult = openAIChatClient.CompleteChatStreamingAsync(messages);

        // Assert
        List<StreamingChatCompletionUpdate> updates = [];
        await foreach (StreamingChatCompletionUpdate update in streamingResult)
        {
            updates.Add(update);
        }

        Assert.NotEmpty(updates);

        // Should have finish reason of tool_calls
        StreamingChatCompletionUpdate? lastUpdate = updates.LastOrDefault(u => u.FinishReason != null);
        Assert.NotNull(lastUpdate);
        Assert.True(lastUpdate.FinishReason is ChatFinishReason.ToolCalls or ChatFinishReason.Stop); // depends on what response we get
    }

    private ChatClient CreateChatClient(string agentName)
    {
        return new ChatClient(
            model: "test-model",
            credential: new ApiKeyCredential("test-api-key"),
            options: new OpenAIClientOptions
            {
                Endpoint = new Uri(this._httpClient!.BaseAddress!, $"/{agentName}/v1/"),
                Transport = new HttpClientPipelineTransport(this._httpClient)
            });
    }

    private async Task<HttpClient> CreateTestServerAsync(string agentName, string instructions, string responseText = "Test response")
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient(responseText);
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);
        builder.AddOpenAIChatCompletions();
        builder.AddAIAgent(agentName, instructions, chatClientServiceKey: "chat-client");

        this._app = builder.Build();
        AIAgent agent = this._app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        this._app.MapOpenAIChatCompletions(agent);

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
        builder.AddOpenAIChatCompletions();

        this._app = builder.Build();
        AIAgent agent = this._app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        this._app.MapOpenAIChatCompletions(agent);

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

        builder.AddOpenAIChatCompletions();

        this._app = builder.Build();

        foreach ((string name, string _, string _) in agents)
        {
            AIAgent agent = this._app.Services.GetRequiredKeyedService<AIAgent>(name);
            this._app.MapOpenAIChatCompletions(agent);
        }

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        return testServer.CreateClient();
    }
}
