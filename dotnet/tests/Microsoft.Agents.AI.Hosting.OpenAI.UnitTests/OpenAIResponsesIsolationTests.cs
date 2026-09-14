// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Hosting.Server;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.TestHost;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Verifies caller isolation for response state and for conversation storage accessed through the Responses API.
/// </summary>
public sealed class OpenAIResponsesIsolationTests : IAsyncDisposable
{
    private const string AgentName = "test-agent";
    private const string UserHeader = "X-Test-User";
    private const string Alice = "alice";
    private const string Bob = "bob";

    private WebApplication? _app;
    private HttpClient? _httpClient;

    [Fact]
    public async Task ResponseState_IsAccessibleOnlyToItsOwnerAsync()
    {
        // Arrange
        HttpClient client = await this.CreateTestServerAsync();
        string responseId = await CreateResponseAsync(client, Alice);

        // Act
        using HttpResponseMessage bobGet = await SendAsync(
            client,
            HttpMethod.Get,
            Bob,
            $"/{AgentName}/v1/responses/{responseId}");
        using HttpResponseMessage bobListItems = await SendAsync(
            client,
            HttpMethod.Get,
            Bob,
            $"/{AgentName}/v1/responses/{responseId}/input_items");
        using HttpResponseMessage bobDelete = await SendAsync(
            client,
            HttpMethod.Delete,
            Bob,
            $"/{AgentName}/v1/responses/{responseId}");
        using HttpResponseMessage bobCancel = await SendAsync(
            client,
            HttpMethod.Post,
            Bob,
            $"/{AgentName}/v1/responses/{responseId}/cancel");
        using HttpResponseMessage bobStream = await SendAsync(
            client,
            HttpMethod.Get,
            Bob,
            $"/{AgentName}/v1/responses/{responseId}?stream=true");

        // Assert
        Assert.Equal(HttpStatusCode.NotFound, bobGet.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, bobListItems.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, bobDelete.StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, bobCancel.StatusCode);
        Assert.Contains(
            $"Response '{responseId}' not found.",
            await bobCancel.Content.ReadAsStringAsync(),
            StringComparison.Ordinal);
        Assert.DoesNotContain(
            responseId,
            await bobStream.Content.ReadAsStringAsync(),
            StringComparison.Ordinal);

        using HttpResponseMessage aliceGet = await SendAsync(
            client,
            HttpMethod.Get,
            Alice,
            $"/{AgentName}/v1/responses/{responseId}");
        Assert.Equal(HttpStatusCode.OK, aliceGet.StatusCode);
        Assert.DoesNotContain("::", responseId, StringComparison.Ordinal);
    }

    [Fact]
    public async Task StreamingResponseState_IsAccessibleOnlyToItsOwnerAsync()
    {
        // Arrange
        HttpClient client = await this.CreateTestServerAsync();
        string body = JsonSerializer.Serialize(new
        {
            metadata = new { entity_id = AgentName },
            input = "Stream this response",
            stream = true
        });

        // Act
        using HttpResponseMessage aliceCreate = await SendAsync(
            client,
            HttpMethod.Post,
            Alice,
            $"/{AgentName}/v1/responses",
            body);
        aliceCreate.EnsureSuccessStatusCode();
        string responseId = GetResponseIdFromSse(await aliceCreate.Content.ReadAsStringAsync());

        using HttpResponseMessage bobGet = await SendAsync(
            client,
            HttpMethod.Get,
            Bob,
            $"/{AgentName}/v1/responses/{responseId}");
        using HttpResponseMessage aliceGet = await SendAsync(
            client,
            HttpMethod.Get,
            Alice,
            $"/{AgentName}/v1/responses/{responseId}");

        // Assert
        Assert.DoesNotContain("::", responseId, StringComparison.Ordinal);
        Assert.Equal(HttpStatusCode.NotFound, bobGet.StatusCode);
        Assert.Equal(HttpStatusCode.OK, aliceGet.StatusCode);
    }

    [Fact]
    public async Task RegisteredResponseService_IsCallerScopedAsync()
    {
        // Arrange
        HttpClient client = await this.CreateTestServerAsync(mapRegisteredResponseService: true);
        string responseId = await CreateResponseAsync(client, Alice, "/v1/responses");

        // Act
        using HttpResponseMessage bobGet = await SendAsync(
            client,
            HttpMethod.Get,
            Bob,
            $"/v1/responses/{responseId}");
        using HttpResponseMessage aliceGet = await SendAsync(
            client,
            HttpMethod.Get,
            Alice,
            $"/v1/responses/{responseId}");

        // Assert
        Assert.Equal(HttpStatusCode.NotFound, bobGet.StatusCode);
        Assert.Equal(HttpStatusCode.OK, aliceGet.StatusCode);
    }

    [Fact]
    public async Task ConversationReference_IsScopedForResponsesAsync()
    {
        // Arrange
        HttpClient client = await this.CreateTestServerAsync();
        string conversationId = await CreateConversationAsync(client, Alice);

        // Act - the owner uses the public conversation ID.
        using HttpResponseMessage aliceCreate = await CreateResponseForConversationAsync(
            client,
            Alice,
            conversationId,
            "Alice's message");

        // Assert - the Responses API resolves the owner's scoped storage entry.
        Assert.Equal(HttpStatusCode.OK, aliceCreate.StatusCode);
        using JsonDocument aliceItems = await GetJsonAsync(
            client,
            Alice,
            $"/v1/conversations/{conversationId}/items");
        Assert.Contains("Alice's message", aliceItems.RootElement.GetRawText(), StringComparison.Ordinal);

        // Act - another caller cannot use either the public ID or a derived internal storage ID.
        using HttpResponseMessage bobBareId = await CreateResponseForConversationAsync(
            client,
            Bob,
            conversationId,
            "Bob's message");
        using HttpResponseMessage bobScopedId = await CreateResponseForConversationAsync(
            client,
            Bob,
            $"{Alice}::{conversationId}",
            "Bob's crafted message");

        // Assert
        Assert.Equal(HttpStatusCode.NotFound, bobBareId.StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, bobScopedId.StatusCode);

        using JsonDocument unchangedAliceItems = await GetJsonAsync(
            client,
            Alice,
            $"/v1/conversations/{conversationId}/items");
        string serializedItems = unchangedAliceItems.RootElement.GetRawText();
        Assert.DoesNotContain("Bob's message", serializedItems, StringComparison.Ordinal);
        Assert.DoesNotContain("Bob's crafted message", serializedItems, StringComparison.Ordinal);
    }

    [Fact]
    public async Task BackgroundResponse_UsesCapturedConversationStorageIdAsync()
    {
        // Arrange
        HttpClient client = await this.CreateTestServerAsync();
        string conversationId = await CreateConversationAsync(client, Alice);
        string requestBody = JsonSerializer.Serialize(new
        {
            metadata = new { entity_id = AgentName },
            conversation = conversationId,
            input = "Background message",
            background = true,
            stream = false
        });

        // Act
        using HttpResponseMessage createResponse = await SendAsync(
            client,
            HttpMethod.Post,
            Alice,
            $"/{AgentName}/v1/responses",
            requestBody);
        createResponse.EnsureSuccessStatusCode();

        using JsonDocument created = JsonDocument.Parse(await createResponse.Content.ReadAsStringAsync());
        string responseId = created.RootElement.GetProperty("id").GetString()!;
        await WaitForResponseCompletionAsync(client, Alice, responseId);

        // Assert
        using JsonDocument items = await GetJsonAsync(
            client,
            Alice,
            $"/v1/conversations/{conversationId}/items");
        Assert.Contains("Background message", items.RootElement.GetRawText(), StringComparison.Ordinal);
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task MissingIsolationKey_FailsClosedAsync(bool mapRegisteredResponseService)
    {
        // Arrange
        HttpClient client = await this.CreateTestServerAsync(mapRegisteredResponseService);
        string body = JsonSerializer.Serialize(new
        {
            metadata = new { entity_id = AgentName },
            input = "Unauthenticated message",
            stream = false
        });

        // Act & Assert
        await Assert.ThrowsAnyAsync<Exception>(async () =>
        {
            using HttpResponseMessage response = await SendAsync(
                client,
                HttpMethod.Post,
                principal: null,
                mapRegisteredResponseService ? "/v1/responses" : $"/{AgentName}/v1/responses",
                body);
            response.EnsureSuccessStatusCode();
        });
    }

    [Fact]
    public async Task WithoutIsolationKeyProvider_ResponsesRemainSharedAsync()
    {
        // Arrange
        HttpClient client = await this.CreateTestServerAsync(withIsolation: false);
        string responseId = await CreateResponseAsync(client, Alice);

        // Act
        using HttpResponseMessage bobGet = await SendAsync(
            client,
            HttpMethod.Get,
            Bob,
            $"/{AgentName}/v1/responses/{responseId}");

        // Assert
        Assert.Equal(HttpStatusCode.OK, bobGet.StatusCode);
    }

    private static async Task<string> CreateConversationAsync(HttpClient client, string principal)
    {
        string body = JsonSerializer.Serialize(new { metadata = new { agent_id = AgentName } });
        using HttpResponseMessage response = await SendAsync(
            client,
            HttpMethod.Post,
            principal,
            "/v1/conversations",
            body);
        response.EnsureSuccessStatusCode();

        using JsonDocument document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        return document.RootElement.GetProperty("id").GetString()!;
    }

    private static async Task<string> CreateResponseAsync(
        HttpClient client,
        string principal,
        string responsesPath = $"/{AgentName}/v1/responses")
    {
        string body = JsonSerializer.Serialize(new
        {
            metadata = new { entity_id = AgentName },
            input = "What is the capital of France?",
            stream = false
        });

        using HttpResponseMessage response = await SendAsync(
            client,
            HttpMethod.Post,
            principal,
            responsesPath,
            body);
        response.EnsureSuccessStatusCode();

        using JsonDocument document = JsonDocument.Parse(await response.Content.ReadAsStringAsync());
        return document.RootElement.GetProperty("id").GetString()!;
    }

    private static Task<HttpResponseMessage> CreateResponseForConversationAsync(
        HttpClient client,
        string principal,
        string conversationId,
        string input)
    {
        string body = JsonSerializer.Serialize(new
        {
            metadata = new { entity_id = AgentName },
            conversation = conversationId,
            input,
            stream = false
        });

        return SendAsync(client, HttpMethod.Post, principal, $"/{AgentName}/v1/responses", body);
    }

    private static async Task WaitForResponseCompletionAsync(
        HttpClient client,
        string principal,
        string responseId)
    {
        for (int attempt = 0; attempt < 100; attempt++)
        {
            using JsonDocument response = await GetJsonAsync(
                client,
                principal,
                $"/{AgentName}/v1/responses/{responseId}");
            string? status = response.RootElement.GetProperty("status").GetString();

            if (status == "completed")
            {
                return;
            }

            if (status is "failed" or "cancelled" or "incomplete")
            {
                throw new InvalidOperationException($"Background response entered terminal status '{status}'.");
            }

            await Task.Delay(TimeSpan.FromMilliseconds(20));
        }

        throw new TimeoutException("Background response did not complete.");
    }

    private static string GetResponseIdFromSse(string content)
    {
        foreach (string line in content.Split('\n'))
        {
            if (!line.StartsWith("data: ", StringComparison.Ordinal))
            {
                continue;
            }

            using JsonDocument data = JsonDocument.Parse(line.Substring("data: ".Length));
            if (data.RootElement.GetProperty("type").GetString() == "response.created")
            {
                return data.RootElement.GetProperty("response").GetProperty("id").GetString()!;
            }
        }

        throw new InvalidOperationException("The stream did not contain a response.created event.");
    }

    private static async Task<JsonDocument> GetJsonAsync(
        HttpClient client,
        string principal,
        string path)
    {
        using HttpResponseMessage response = await SendAsync(client, HttpMethod.Get, principal, path);
        response.EnsureSuccessStatusCode();
        return JsonDocument.Parse(await response.Content.ReadAsStringAsync());
    }

    private static async Task<HttpResponseMessage> SendAsync(
        HttpClient client,
        HttpMethod method,
        string? principal,
        string path,
        string? body = null)
    {
        using var request = new HttpRequestMessage(method, new Uri(path, UriKind.Relative));
        if (principal is not null)
        {
            request.Headers.Add(UserHeader, principal);
        }

        if (body is not null)
        {
            request.Content = new StringContent(body, Encoding.UTF8, "application/json");
        }

        return await client.SendAsync(request);
    }

    private async Task<HttpClient> CreateTestServerAsync(
        bool mapRegisteredResponseService = false,
        bool withIsolation = true)
    {
        WebApplicationBuilder builder = WebApplication.CreateBuilder();
        builder.WebHost.UseTestServer();

        builder.Services.AddKeyedSingleton<IChatClient>(
            "chat-client",
            new TestHelpers.SimpleMockChatClient("The capital of France is Paris."));
        builder.AddAIAgent(
            AgentName,
            "You are a helpful assistant.",
            chatClientServiceKey: "chat-client");

        if (withIsolation)
        {
            builder.Services.AddHttpContextAccessor();
            builder.Services.AddSingleton<AgentIsolationKeyProvider, HeaderAgentIsolationKeyProvider>();
        }
        builder.AddOpenAIConversations();
        builder.AddOpenAIResponses();

        this._app = builder.Build();

        AIAgent agent = this._app.Services.GetRequiredKeyedService<AIAgent>(AgentName);
        this._app.MapOpenAIConversations();
        if (mapRegisteredResponseService)
        {
            this._app.MapOpenAIResponses();
        }
        else
        {
            this._app.MapOpenAIResponses(agent);
        }

        await this._app.StartAsync();

        TestServer testServer = this._app.Services.GetRequiredService<IServer>() as TestServer
            ?? throw new InvalidOperationException("TestServer not found");

        this._httpClient = testServer.CreateClient();
        return this._httpClient;
    }

    public async ValueTask DisposeAsync()
    {
        this._httpClient?.Dispose();

        if (this._app is not null)
        {
            await this._app.DisposeAsync();
        }

        GC.SuppressFinalize(this);
    }

    private sealed class HeaderAgentIsolationKeyProvider : AgentIsolationKeyProvider
    {
        private readonly IHttpContextAccessor _httpContextAccessor;

        public HeaderAgentIsolationKeyProvider(IHttpContextAccessor httpContextAccessor)
        {
            this._httpContextAccessor = httpContextAccessor;
        }

        public override ValueTask<string?> GetIsolationKeyAsync(CancellationToken cancellationToken = default)
        {
            string? key = this._httpContextAccessor.HttpContext?.Request.Headers[UserHeader].ToString();
            return new ValueTask<string?>(string.IsNullOrEmpty(key) ? null : key);
        }
    }
}
