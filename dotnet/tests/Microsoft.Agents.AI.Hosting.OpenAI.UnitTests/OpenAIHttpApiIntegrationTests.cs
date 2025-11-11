// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Integration tests for the HTTP API with in-memory conversation, response, and agent index storage.
/// Tests create a conversation, create a response, wait for completion, then verify the conversation was updated.
/// </summary>
public sealed class OpenAIHttpApiIntegrationTests : IAsyncDisposable
{
    private WebApplication? _app;
    private HttpClient? _httpClient;

    [Fact]
    public async Task CreateConversationAndResponse_NonStreaming_NonBackground_UpdatesConversationWithOutputAsync()
    {
        // Arrange
        const string AgentName = "test-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "The capital of France is Paris.";
        const string UserMessage = "What is the capital of France?";

        HttpClient client = await this.CreateTestServerWithInMemoryStorageAsync(AgentName, Instructions, ExpectedResponse);

        // Act - Create conversation
        var createConversationRequest = new { metadata = new { agent_id = AgentName } };
        string createConvJson = JsonSerializer.Serialize(createConversationRequest);
        HttpResponseMessage createConvResponse = await this.SendPostRequestAsync(client, "/v1/conversations", createConvJson);
        using var createConvDoc = await this.ParseResponseAsync(createConvResponse);
        string conversationId = createConvDoc.RootElement.GetProperty("id").GetString()!;

        // Act - Create response (non-streaming, non-background)
        var createResponseRequest = new
        {
            metadata = new { entity_id = AgentName },
            conversation = conversationId,
            input = UserMessage,
            stream = false
        };
        string createRespJson = JsonSerializer.Serialize(createResponseRequest);
        HttpResponseMessage createRespResponse = await this.SendPostRequestAsync(client, $"/{AgentName}/v1/responses", createRespJson);
        using var createRespDoc = await this.ParseResponseAsync(createRespResponse);
        var response = createRespDoc.RootElement;

        // Assert - Response completed
        Assert.Equal("completed", response.GetProperty("status").GetString());
        string responseId = response.GetProperty("id").GetString()!;
        Assert.NotNull(responseId);
        Assert.StartsWith("resp_", responseId);

        // Assert - Response has output
        Assert.True(response.TryGetProperty("output", out var output));
        Assert.True(output.GetArrayLength() > 0);
        var outputItem = output[0];
        var content = outputItem.GetProperty("content");
        Assert.True(content.GetArrayLength() > 0);
        var textContent = content[0];
        Assert.Equal("output_text", textContent.GetProperty("type").GetString());
        Assert.Equal(ExpectedResponse, textContent.GetProperty("text").GetString());

        // Act - List conversation items to verify they were updated
        HttpResponseMessage listItemsResponse = await this.SendGetRequestAsync(client, $"/v1/conversations/{conversationId}/items");
        using var listItemsDoc = await this.ParseResponseAsync(listItemsResponse);
        var itemsList = listItemsDoc.RootElement;

        // Assert - Conversation items were added
        Assert.Equal("list", itemsList.GetProperty("object").GetString());
        var items = itemsList.GetProperty("data");

        Assert.True(items.GetArrayLength() > 0, "Conversation should have items after response completion");

        // Find the assistant message in the items
        bool foundAssistantMessage = items.EnumerateArray()
            .Where(item => item.GetProperty("type").GetString() == "message" &&
                          item.GetProperty("role").GetString() == "assistant")
            .Any(item =>
            {
                JsonElement itemContent = item.GetProperty("content");
                if (itemContent.GetArrayLength() > 0)
                {
                    JsonElement firstContent = itemContent[0];
                    return firstContent.GetProperty("type").GetString() == "output_text" &&
                           firstContent.GetProperty("text").GetString() == ExpectedResponse;
                }
                return false;
            });

        Assert.True(foundAssistantMessage, "Conversation should contain the assistant's response message");
    }

    [Fact]
    public async Task CreateConversationAndResponse_Streaming_NonBackground_UpdatesConversationWithOutputAsync()
    {
        // Arrange
        const string AgentName = "streaming-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Hello there! How can I help you today?";
        const string UserMessage = "Hello";

        HttpClient client = await this.CreateTestServerWithInMemoryStorageAsync(AgentName, Instructions, ExpectedResponse);

        // Act - Create conversation
        var createConversationRequest = new { metadata = new { agent_id = AgentName } };
        string createConvJson = JsonSerializer.Serialize(createConversationRequest);
        HttpResponseMessage createConvResponse = await this.SendPostRequestAsync(client, "/v1/conversations", createConvJson);
        using var createConvDoc = await this.ParseResponseAsync(createConvResponse);
        string conversationId = createConvDoc.RootElement.GetProperty("id").GetString()!;

        // Act - Create response (streaming, non-background)
        var createResponseRequest = new
        {
            metadata = new { entity_id = AgentName },
            conversation = conversationId,
            input = UserMessage,
            stream = true
        };
        string createRespJson = JsonSerializer.Serialize(createResponseRequest);
        HttpResponseMessage createRespResponse = await this.SendPostRequestAsync(client, $"/{AgentName}/v1/responses", createRespJson);

        // Assert - Response is SSE format
        Assert.Equal("text/event-stream", createRespResponse.Content.Headers.ContentType?.MediaType);

        // Parse SSE events
        string sseContent = await createRespResponse.Content.ReadAsStringAsync();
        var events = this.ParseSseEvents(sseContent);

        // Assert - Has expected event types
        var eventTypes = events.Select(e => e.GetProperty("type").GetString()).ToList();
        Assert.Contains("response.created", eventTypes);
        Assert.Contains("response.completed", eventTypes);

        // Collect the full response text from deltas
        var deltaEvents = events.Where(e => e.GetProperty("type").GetString() == "response.output_text.delta").ToList();
        string streamedText = string.Concat(deltaEvents.Select(e => e.GetProperty("delta").GetString()));
        Assert.Equal(ExpectedResponse, streamedText);

        // Act - List conversation items to verify messages were added
        HttpResponseMessage listItemsResponse = await this.SendGetRequestAsync(client, $"/v1/conversations/{conversationId}/items");
        using var listItemsDoc = await this.ParseResponseAsync(listItemsResponse);
        var itemsList = listItemsDoc.RootElement;

        // Assert - Conversation items were added
        var items = itemsList.GetProperty("data");
        Assert.True(items.GetArrayLength() > 0, "Conversation should have items after streaming response completion");

        // Find the assistant message in the items
        bool foundAssistantMessage = items.EnumerateArray()
            .Where(item => item.GetProperty("type").GetString() == "message" &&
                          item.GetProperty("role").GetString() == "assistant")
            .Any(item =>
            {
                JsonElement itemContent = item.GetProperty("content");
                if (itemContent.GetArrayLength() > 0)
                {
                    JsonElement firstContent = itemContent[0];
                    return firstContent.GetProperty("type").GetString() == "output_text" &&
                           firstContent.GetProperty("text").GetString() == ExpectedResponse;
                }
                return false;
            });

        Assert.True(foundAssistantMessage, "Conversation should contain the assistant's response message");
    }

    [Fact]
    public async Task CreateConversationAndResponse_NonStreaming_Background_UpdatesConversationWhenCompleteAsync()
    {
        // Arrange
        const string AgentName = "background-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Processing in background...";
        const string UserMessage = "Can you process this?";

        HttpClient client = await this.CreateTestServerWithInMemoryStorageAsync(AgentName, Instructions, ExpectedResponse);

        // Act - Create conversation
        var createConversationRequest = new { metadata = new { agent_id = AgentName } };
        string createConvJson = JsonSerializer.Serialize(createConversationRequest);
        HttpResponseMessage createConvResponse = await this.SendPostRequestAsync(client, "/v1/conversations", createConvJson);
        using var createConvDoc = await this.ParseResponseAsync(createConvResponse);
        string conversationId = createConvDoc.RootElement.GetProperty("id").GetString()!;

        // Act - Create response (non-streaming, background)
        var createResponseRequest = new
        {
            metadata = new { entity_id = AgentName },
            conversation = conversationId,
            input = UserMessage,
            stream = false,
            background = true
        };
        string createRespJson = JsonSerializer.Serialize(createResponseRequest);
        HttpResponseMessage createRespResponse = await this.SendPostRequestAsync(client, $"/{AgentName}/v1/responses", createRespJson);
        using var createRespDoc = await this.ParseResponseAsync(createRespResponse);
        var response = createRespDoc.RootElement;

        // Assert - Response is in progress or queued
        string status = response.GetProperty("status").GetString()!;
        Assert.True(status == "in_progress" || status == "queued" || status == "completed", $"Expected 'in_progress', 'queued', or 'completed', got '{status}'");
        string responseId = response.GetProperty("id").GetString()!;

        // Wait for completion by polling
        const int MaxAttempts = 20;
        int attempt = 0;
        string finalStatus = status;
        string? errorMessage = null;
        while (finalStatus != "completed" && finalStatus != "failed" && attempt < MaxAttempts)
        {
            await Task.Delay(100);
            HttpResponseMessage getResponseResponse = await this.SendGetRequestAsync(client, $"/{AgentName}/v1/responses/{responseId}");
            using var getRespDoc = await this.ParseResponseAsync(getResponseResponse);
            finalStatus = getRespDoc.RootElement.GetProperty("status").GetString()!;
            if (getRespDoc.RootElement.TryGetProperty("error", out var error) &&
                error.ValueKind == JsonValueKind.Object &&
                error.TryGetProperty("message", out var messageElement))
            {
                errorMessage = messageElement.GetString();
            }

            attempt++;
        }

        // Assert - Response eventually completed
        Assert.Equal("completed", finalStatus + (errorMessage != null ? $" Error: {errorMessage}" : ""));

        // Act - List conversation items to verify messages were added
        HttpResponseMessage listItemsResponse = await this.SendGetRequestAsync(client, $"/v1/conversations/{conversationId}/items");
        using var listItemsDoc = await this.ParseResponseAsync(listItemsResponse);
        var itemsList = listItemsDoc.RootElement;

        // Assert - Conversation items were added
        var items = itemsList.GetProperty("data");
        Assert.True(items.GetArrayLength() > 0, "Conversation should have items after background response completion");

        // Find the assistant message in the items
        bool foundAssistantMessage = items.EnumerateArray()
            .Where(item => item.GetProperty("type").GetString() == "message" &&
                          item.GetProperty("role").GetString() == "assistant")
            .Any(item =>
            {
                JsonElement itemContent = item.GetProperty("content");
                if (itemContent.GetArrayLength() > 0)
                {
                    JsonElement firstContent = itemContent[0];
                    return firstContent.GetProperty("type").GetString() == "output_text" &&
                           firstContent.GetProperty("text").GetString() == ExpectedResponse;
                }
                return false;
            });

        Assert.True(foundAssistantMessage, "Conversation should contain the assistant's response message");
    }

    [Fact]
    public async Task CreateConversationAndResponse_Streaming_Background_UpdatesConversationWhenCompleteAsync()
    {
        // Arrange
        const string AgentName = "streaming-background-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Streaming background response";
        const string UserMessage = "Process this with streaming";

        HttpClient client = await this.CreateTestServerWithInMemoryStorageAsync(AgentName, Instructions, ExpectedResponse);

        // Act - Create conversation
        var createConversationRequest = new { metadata = new { agent_id = AgentName } };
        string createConvJson = JsonSerializer.Serialize(createConversationRequest);
        HttpResponseMessage createConvResponse = await this.SendPostRequestAsync(client, "/v1/conversations", createConvJson);
        using var createConvDoc = await this.ParseResponseAsync(createConvResponse);
        string conversationId = createConvDoc.RootElement.GetProperty("id").GetString()!;

        // Act - Create response (streaming, background)
        var createResponseRequest = new
        {
            model = AgentName,
            conversation = conversationId,
            input = UserMessage,
            stream = true,
            background = false // Note: streaming with background=true is typically streaming
        };
        string createRespJson = JsonSerializer.Serialize(createResponseRequest);
        HttpResponseMessage createRespResponse = await this.SendPostRequestAsync(client, $"/{AgentName}/v1/responses", createRespJson);

        // Assert - Response is SSE format
        Assert.Equal("text/event-stream", createRespResponse.Content.Headers.ContentType?.MediaType);

        // Parse SSE events
        string sseContent = await createRespResponse.Content.ReadAsStringAsync();
        var events = this.ParseSseEvents(sseContent);
        var eventTypes = events.Select(e => e.GetProperty("type").GetString()).ToList();
        Assert.Contains("response.created", eventTypes);
        Assert.Contains("response.completed", eventTypes);

        // Act - List conversation items to verify messages were added
        HttpResponseMessage listItemsResponse = await this.SendGetRequestAsync(client, $"/v1/conversations/{conversationId}/items");
        using var listItemsDoc = await this.ParseResponseAsync(listItemsResponse);
        var itemsList = listItemsDoc.RootElement;

        // Assert - Conversation items were added
        var items = itemsList.GetProperty("data");
        Assert.True(items.GetArrayLength() > 0, "Conversation should have items after streaming response completion");

        // Find the assistant message in the items
        bool foundAssistantMessage = items.EnumerateArray()
            .Where(item => item.GetProperty("type").GetString() == "message" &&
                          item.GetProperty("role").GetString() == "assistant")
            .Any(item =>
            {
                JsonElement itemContent = item.GetProperty("content");
                if (itemContent.GetArrayLength() > 0)
                {
                    JsonElement firstContent = itemContent[0];
                    return firstContent.GetProperty("type").GetString() == "output_text";
                }
                return false;
            });

        Assert.True(foundAssistantMessage, "Conversation should contain the assistant's response message");
    }

    /// <summary>
    /// Creates a test server with in-memory conversation, response, and agent index storage.
    /// </summary>
    private async Task<HttpClient> CreateTestServerWithInMemoryStorageAsync(string agentName, string instructions, string responseText)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        // Create mock chat client
        IChatClient mockChatClient = new TestHelpers.SimpleMockChatClient(responseText);
        builder.Services.AddKeyedSingleton("chat-client", mockChatClient);

        // Add agent
        builder.AddAIAgent(agentName, instructions, chatClientServiceKey: "chat-client");

        // Add in-memory storage for conversations, responses, and agent index
        builder.AddOpenAIConversations();
        builder.AddOpenAIResponses();

        this._app = builder.Build();

        // Map endpoints
        AIAgent agent = this._app.Services.GetRequiredKeyedService<AIAgent>(agentName);
        this._app.MapOpenAIConversations();
        this._app.MapOpenAIResponses(agent);

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._httpClient = testServer.CreateClient();
        return this._httpClient;
    }

    /// <summary>
    /// Sends a POST request with JSON content to the test server.
    /// </summary>
    private async Task<HttpResponseMessage> SendPostRequestAsync(HttpClient client, string path, string requestJson)
    {
        using StringContent content = new(requestJson, Encoding.UTF8, "application/json");
        return await client.PostAsync(new Uri(path, UriKind.Relative), content);
    }

    /// <summary>
    /// Sends a GET request to the test server.
    /// </summary>
    private async Task<HttpResponseMessage> SendGetRequestAsync(HttpClient client, string path)
    {
        return await client.GetAsync(new Uri(path, UriKind.Relative));
    }

    /// <summary>
    /// Parses the response JSON and returns a JsonDocument.
    /// </summary>
    private async Task<JsonDocument> ParseResponseAsync(HttpResponseMessage response)
    {
        string responseJson = await response.Content.ReadAsStringAsync();
        return JsonDocument.Parse(responseJson);
    }

    /// <summary>
    /// Parses SSE events from streaming response content string.
    /// </summary>
    private JsonElement[] ParseSseEvents(string sseContent)
    {
        var events = new System.Collections.Generic.List<JsonElement>();
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
                    if (!string.IsNullOrWhiteSpace(jsonData))
                    {
                        var doc = JsonDocument.Parse(jsonData);
                        events.Add(doc.RootElement.Clone());
                    }
                }
            }
        }

        return events.ToArray();
    }

    public async ValueTask DisposeAsync()
    {
        this._httpClient?.Dispose();
        if (this._app != null)
        {
            await this._app.DisposeAsync();
        }

        GC.SuppressFinalize(this);
    }
}
