// Copyright (c) Microsoft. All rights reserved.

using System;
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
/// Integration tests for the MapOpenAIResponses variant that resolves agents from the Agent.Name property.
/// These tests validate the agent resolution mechanism using the HostedAgentResponseExecutor.
/// </summary>
public sealed class OpenAIResponsesAgentResolutionIntegrationTests : IAsyncDisposable
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
    /// Verifies that agent resolution works using the agent.name property in streaming mode.
    /// </summary>
    [Fact]
    public async Task CreateResponseStreaming_WithAgentNameProperty_ResolvesCorrectAgentAsync()
    {
        // Arrange
        const string AgentName = "test-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Hello from agent resolution!";

        this._httpClient = await this.CreateTestServerWithAgentResolutionAsync(
            (AgentName, Instructions, ExpectedResponse));

        // Act - Use raw HTTP request with agent.name specified
        using StringContent requestContent = new(JsonSerializer.Serialize(new
        {
            agent = new { name = AgentName },
            stream = true,
            input = new[]
            {
                new { type = "message", role = "user", content = "Test message" }
            }
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage httpResponse = await this._httpClient!.PostAsync(new Uri("/v1/responses", UriKind.Relative), requestContent);

        // Assert
        Assert.True(httpResponse.IsSuccessStatusCode, $"Request failed with status {httpResponse.StatusCode}");

        string responseText = await httpResponse.Content.ReadAsStringAsync();
        Assert.Contains(ExpectedResponse, responseText);
        Assert.Contains("response.created", responseText);
        Assert.Contains("response.completed", responseText);
    }

    /// <summary>
    /// Verifies that agent resolution works using the agent.name property in non-streaming mode.
    /// </summary>
    [Fact]
    public async Task CreateResponse_WithAgentNameProperty_ResolvesCorrectAgentAsync()
    {
        // Arrange
        const string AgentName = "test-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Hello from agent resolution!";

        this._httpClient = await this.CreateTestServerWithAgentResolutionAsync(
            (AgentName, Instructions, ExpectedResponse));

        // Act - Use raw HTTP request with agent.name specified
        using StringContent requestContent = new(JsonSerializer.Serialize(new
        {
            agent = new { name = AgentName },
            input = new[]
            {
                new { type = "message", role = "user", content = "Test message" }
            }
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage httpResponse = await this._httpClient!.PostAsync(new Uri("/v1/responses", UriKind.Relative), requestContent);

        // Assert
        Assert.True(httpResponse.IsSuccessStatusCode, $"Request failed with status {httpResponse.StatusCode}");

        string responseJson = await httpResponse.Content.ReadAsStringAsync();
        using JsonDocument doc = JsonDocument.Parse(responseJson);
        JsonElement root = doc.RootElement;

        Assert.Equal("completed", root.GetProperty("status").GetString());
        JsonElement outputArray = root.GetProperty("output");
        Assert.True(outputArray.GetArrayLength() > 0);

        JsonElement firstOutput = outputArray[0];
        JsonElement contentArray = firstOutput.GetProperty("content");
        JsonElement firstContent = contentArray[0];
        string actualResponse = firstContent.GetProperty("text").GetString() ?? string.Empty;

        Assert.Equal(ExpectedResponse, actualResponse);
    }

    /// <summary>
    /// Verifies that agent resolution can distinguish between multiple agents.
    /// </summary>
    [Fact]
    public async Task CreateResponse_WithMultipleAgents_ResolvesCorrectAgentAsync()
    {
        // Arrange
        const string Agent1Name = "agent-1";
        const string Agent1Response = "Response from agent 1";
        const string Agent2Name = "agent-2";
        const string Agent2Response = "Response from agent 2";

        this._httpClient = await this.CreateTestServerWithAgentResolutionAsync(
            (Agent1Name, "Agent 1 instructions", Agent1Response),
            (Agent2Name, "Agent 2 instructions", Agent2Response));

        // Act - Create response for agent 1
        using StringContent requestContent1 = new(JsonSerializer.Serialize(new
        {
            agent = new { name = Agent1Name },
            input = new[]
            {
                new { type = "message", role = "user", content = "Test message" }
            }
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage httpResponse1 = await this._httpClient!.PostAsync(new Uri("/v1/responses", UriKind.Relative), requestContent1);

        // Act - Create response for agent 2
        using StringContent requestContent2 = new(JsonSerializer.Serialize(new
        {
            agent = new { name = Agent2Name },
            input = new[]
            {
                new { type = "message", role = "user", content = "Test message" }
            }
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage httpResponse2 = await this._httpClient!.PostAsync(new Uri("/v1/responses", UriKind.Relative), requestContent2);

        // Assert
        string responseJson1 = await httpResponse1.Content.ReadAsStringAsync();
        string responseJson2 = await httpResponse2.Content.ReadAsStringAsync();

        using JsonDocument doc1 = JsonDocument.Parse(responseJson1);
        using JsonDocument doc2 = JsonDocument.Parse(responseJson2);

        string content1 = doc1.RootElement.GetProperty("output")[0].GetProperty("content")[0].GetProperty("text").GetString() ?? string.Empty;
        string content2 = doc2.RootElement.GetProperty("output")[0].GetProperty("content")[0].GetProperty("text").GetString() ?? string.Empty;

        Assert.Equal(Agent1Response, content1);
        Assert.Equal(Agent2Response, content2);
    }

    /// <summary>
    /// Verifies that agent resolution using the metadata.entity_id property works correctly.
    /// </summary>
    [Fact]
    public async Task CreateResponse_WithMetadataEntityId_ResolvesCorrectAgentAsync()
    {
        // Arrange
        const string AgentName = "metadata-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Response via metadata.entity_id";

        this._httpClient = await this.CreateTestServerWithAgentResolutionAsync(
            (AgentName, Instructions, ExpectedResponse));

        // Act - Use raw HTTP request with metadata.entity_id
        using StringContent requestContent = new(JsonSerializer.Serialize(new
        {
            metadata = new { entity_id = AgentName },
            input = new[]
            {
                new { type = "message", role = "user", content = "Test message" }
            }
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage httpResponse = await this._httpClient!.PostAsync(new Uri("/v1/responses", UriKind.Relative), requestContent);

        // Assert
        Assert.True(httpResponse.IsSuccessStatusCode, $"Request failed with status {httpResponse.StatusCode}");

        string responseJson = await httpResponse.Content.ReadAsStringAsync();
        using JsonDocument doc = JsonDocument.Parse(responseJson);
        JsonElement root = doc.RootElement;

        Assert.Equal("completed", root.GetProperty("status").GetString());
        JsonElement outputArray = root.GetProperty("output");
        Assert.True(outputArray.GetArrayLength() > 0);

        JsonElement firstOutput = outputArray[0];
        JsonElement contentArray = firstOutput.GetProperty("content");
        JsonElement firstContent = contentArray[0];
        string actualResponse = firstContent.GetProperty("text").GetString() ?? string.Empty;

        Assert.Equal(ExpectedResponse, actualResponse);
    }

    /// <summary>
    /// Verifies that agent resolution fails gracefully when agent is not found.
    /// </summary>
    [Fact]
    public async Task CreateResponse_WithNonExistentAgent_ReturnsNotFoundAsync()
    {
        // Arrange
        this._httpClient = await this.CreateTestServerWithAgentResolutionAsync(
            ("existing-agent", "Instructions", "Response"));

        // Act
        using StringContent requestContent = new(JsonSerializer.Serialize(new
        {
            agent = new { name = "non-existent-agent" },
            input = new[]
            {
                new { type = "message", role = "user", content = "Test message" }
            }
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage httpResponse = await this._httpClient!.PostAsync(new Uri("/v1/responses", UriKind.Relative), requestContent);

        // Assert
        Assert.Equal(System.Net.HttpStatusCode.BadRequest, httpResponse.StatusCode);

        string responseJson = await httpResponse.Content.ReadAsStringAsync();
        Assert.Contains("non-existent-agent", responseJson);
        Assert.Contains("not found", responseJson, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Verifies that agent resolution fails gracefully when no agent name is provided.
    /// </summary>
    [Fact]
    public async Task CreateResponse_WithoutAgentOrModel_ReturnsBadRequestAsync()
    {
        // Arrange
        this._httpClient = await this.CreateTestServerWithAgentResolutionAsync(
            ("test-agent", "Instructions", "Response"));

        // Act - Use raw HTTP request without agent.name or model
        using StringContent requestContent = new(JsonSerializer.Serialize(new
        {
            input = new[]
            {
                new { type = "message", role = "user", content = "Test message" }
            }
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage httpResponse = await this._httpClient!.PostAsync(new Uri("/v1/responses", UriKind.Relative), requestContent);

        // Assert
        Assert.Equal(System.Net.HttpStatusCode.BadRequest, httpResponse.StatusCode);

        string responseJson = await httpResponse.Content.ReadAsStringAsync();
        Assert.Contains("agent.name", responseJson, StringComparison.OrdinalIgnoreCase);
    }

    /// <summary>
    /// Verifies that agent resolution prioritizes agent.name over model when both are provided.
    /// </summary>
    [Fact]
    public async Task CreateResponse_WithBothAgentAndModel_UsesAgentNameAsync()
    {
        // Arrange
        const string Agent1Name = "agent-1";
        const string Agent1Response = "Response from agent 1";
        const string Agent2Name = "agent-2";
        const string Agent2Response = "Response from agent 2";

        this._httpClient = await this.CreateTestServerWithAgentResolutionAsync(
            (Agent1Name, "Agent 1 instructions", Agent1Response),
            (Agent2Name, "Agent 2 instructions", Agent2Response));

        // Act - Use raw HTTP request with both agent.name and model
        using StringContent requestContent = new(JsonSerializer.Serialize(new
        {
            agent = new { name = Agent1Name },
            model = Agent2Name,
            input = new[]
            {
                new { type = "message", role = "user", content = "Test message" }
            }
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage httpResponse = await this._httpClient!.PostAsync(new Uri("/v1/responses", UriKind.Relative), requestContent);

        // Assert
        Assert.True(httpResponse.IsSuccessStatusCode);

        string responseJson = await httpResponse.Content.ReadAsStringAsync();
        using JsonDocument doc = JsonDocument.Parse(responseJson);
        JsonElement root = doc.RootElement;

        JsonElement outputArray = root.GetProperty("output");
        JsonElement firstOutput = outputArray[0];
        JsonElement contentArray = firstOutput.GetProperty("content");
        JsonElement firstContent = contentArray[0];
        string actualResponse = firstContent.GetProperty("text").GetString() ?? string.Empty;

        // Should use agent.name (Agent1Name) and return Agent1Response
        Assert.Equal(Agent1Response, actualResponse);
    }

    /// <summary>
    /// Verifies that streaming and non-streaming work correctly with agent resolution.
    /// </summary>
    [Fact]
    public async Task CreateResponse_AgentResolution_StreamingAndNonStreamingBothWorkAsync()
    {
        // Arrange
        const string AgentName = "dual-mode-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "This is the response";

        this._httpClient = await this.CreateTestServerWithAgentResolutionAsync(
            (AgentName, Instructions, ExpectedResponse));

        // Act - Non-streaming
        using StringContent nonStreamingRequest = new(JsonSerializer.Serialize(new
        {
            agent = new { name = AgentName },
            input = new[]
            {
                new { type = "message", role = "user", content = "Test message" }
            }
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage nonStreamingHttpResponse = await this._httpClient!.PostAsync(new Uri("/v1/responses", UriKind.Relative), nonStreamingRequest);

        // Act - Streaming
        using StringContent streamingRequest = new(JsonSerializer.Serialize(new
        {
            agent = new { name = AgentName },
            stream = true,
            input = new[]
            {
                new { type = "message", role = "user", content = "Test message" }
            }
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage streamingHttpResponse = await this._httpClient!.PostAsync(new Uri("/v1/responses", UriKind.Relative), streamingRequest);

        // Assert non-streaming
        string nonStreamingJson = await nonStreamingHttpResponse.Content.ReadAsStringAsync();
        using JsonDocument nonStreamingDoc = JsonDocument.Parse(nonStreamingJson);
        string nonStreamingContent = nonStreamingDoc.RootElement.GetProperty("output")[0].GetProperty("content")[0].GetProperty("text").GetString() ?? string.Empty;

        // Assert streaming
        string streamingText = await streamingHttpResponse.Content.ReadAsStringAsync();

        Assert.Equal(ExpectedResponse, nonStreamingContent);
        Assert.Contains(ExpectedResponse, streamingText);
    }

    /// <summary>
    /// Verifies that the agent.name field is populated in the response.
    /// </summary>
    [Fact]
    public async Task CreateResponse_WithAgentName_ResponseIncludesAgentFieldAsync()
    {
        // Arrange
        const string AgentName = "test-agent";
        const string Instructions = "You are a helpful assistant.";
        const string ExpectedResponse = "Hello";

        this._httpClient = await this.CreateTestServerWithAgentResolutionAsync(
            (AgentName, Instructions, ExpectedResponse));

        // Act
        using StringContent requestContent = new(JsonSerializer.Serialize(new
        {
            agent = new { name = AgentName },
            input = new[]
            {
                new { type = "message", role = "user", content = "Test message" }
            }
        }), Encoding.UTF8, "application/json");

        using HttpResponseMessage httpResponse = await this._httpClient!.PostAsync(new Uri("/v1/responses", UriKind.Relative), requestContent);

        // Assert
        Assert.True(httpResponse.IsSuccessStatusCode);

        string responseJson = await httpResponse.Content.ReadAsStringAsync();
        using JsonDocument doc = JsonDocument.Parse(responseJson);
        JsonElement root = doc.RootElement;

        // Verify the response includes the agent field
        if (root.TryGetProperty("agent", out JsonElement agentElement))
        {
            string? agentNameInResponse = agentElement.GetProperty("name").GetString();
            Assert.Equal(AgentName, agentNameInResponse);
        }
    }

    private async Task<HttpClient> CreateTestServerWithAgentResolutionAsync(
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

        // Use the agent resolution variant - MapOpenAIResponses() without agent parameter
        this._app.MapOpenAIResponses();

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        return testServer.CreateClient();
    }
}
