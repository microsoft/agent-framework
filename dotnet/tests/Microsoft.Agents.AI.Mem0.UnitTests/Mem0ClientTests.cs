// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.Mem0.UnitTests;

/// <summary>
/// Tests for <see cref="Mem0Client"/>.
/// </summary>
public sealed class Mem0ClientTests : IDisposable
{
    private readonly RecordingHandler _handler = new();
    private readonly HttpClient _httpClient;
    private readonly Mem0Client _client;
    private bool _disposed;

    public Mem0ClientTests()
    {
        this._httpClient = new HttpClient(this._handler)
        {
            BaseAddress = new Uri("https://localhost/")
        };
        this._client = new Mem0Client(this._httpClient);
    }

    #region ClearMemoryAsync Tests

    [Fact]
    public async Task ClearMemoryAsync_BuildsExpectedQueryString_ForPlainScopeValuesAsync()
    {
        // Act
        await this._client.ClearMemoryAsync("myapp", null, null, "alice", CancellationToken.None);

        // Assert
        Assert.Single(this._handler.Requests);
        var requestUri = this._handler.Requests[0].RequestMessage.RequestUri!;
        Assert.Equal(HttpMethod.Delete, this._handler.Requests[0].RequestMessage.Method);
        Assert.Equal("/v1/memories/", requestUri.AbsolutePath);
        Assert.Equal("?app_id=myapp&user_id=alice", requestUri.Query);
    }

    [Fact]
    public async Task ClearMemoryAsync_EncodesScopeValues_ContainingQueryStringMetacharactersAsync()
    {
        // Act
        await this._client.ClearMemoryAsync("myapp", null, null, "alice&app_id=other-tenant-app", CancellationToken.None);

        // Assert
        Assert.Single(this._handler.Requests);
        var requestUri = this._handler.Requests[0].RequestMessage.RequestUri!;

        // The malicious value must be encoded as an opaque user_id value, not interpreted as
        // an additional query parameter. Only a single app_id parameter should be present.
        var queryParts = requestUri.Query.TrimStart('?').Split('&');
        Assert.Equal(2, queryParts.Length);
        Assert.Contains("app_id=myapp", queryParts);
        Assert.Contains("user_id=alice%26app_id%3Dother-tenant-app", queryParts);
    }

    [Fact]
    public async Task ClearMemoryAsync_EncodesAllFourScopeValues_WhenTheyContainReservedCharactersAsync()
    {
        // Act
        await this._client.ClearMemoryAsync("app&x=1", "agent=2", "thread&y", "user=3", CancellationToken.None);

        // Assert
        Assert.Single(this._handler.Requests);
        var requestUri = this._handler.Requests[0].RequestMessage.RequestUri!;
        var queryParts = requestUri.Query.TrimStart('?').Split('&');

        Assert.Equal(4, queryParts.Length);
        Assert.Contains($"app_id={Uri.EscapeDataString("app&x=1")}", queryParts);
        Assert.Contains($"agent_id={Uri.EscapeDataString("agent=2")}", queryParts);
        Assert.Contains($"run_id={Uri.EscapeDataString("thread&y")}", queryParts);
        Assert.Contains($"user_id={Uri.EscapeDataString("user=3")}", queryParts);
    }

    [Fact]
    public async Task ClearMemoryAsync_ProducesNoQueryParameters_WhenNoScopeValuesProvidedAsync()
    {
        // Act
        await this._client.ClearMemoryAsync(null, null, null, null, CancellationToken.None);

        // Assert
        Assert.Single(this._handler.Requests);
        var requestUri = this._handler.Requests[0].RequestMessage.RequestUri!;
        Assert.Equal("/v1/memories/", requestUri.AbsolutePath);
        Assert.Equal("?", requestUri.Query);
    }

    [Fact]
    public async Task ClearMemoryAsync_Throws_WhenServerReturnsErrorStatusAsync()
    {
        // Arrange
        this._handler.EnqueueEmptyResponse(HttpStatusCode.InternalServerError);

        // Act & Assert
        await Assert.ThrowsAsync<HttpRequestException>(() => this._client.ClearMemoryAsync("myapp", null, null, null, CancellationToken.None));
    }

    #endregion

    #region SearchAsync Tests

    [Fact]
    public async Task SearchAsync_Throws_WhenAllScopeValuesMissingAsync()
    {
        // Act & Assert
        var ex = await Assert.ThrowsAsync<ArgumentException>(() => this._client.SearchAsync(null, null, null, null, "query", CancellationToken.None));
        Assert.StartsWith("At least one of applicationId, agentId, threadId, or userId must be provided.", ex.Message);
        Assert.Empty(this._handler.Requests);
    }

    [Fact]
    public async Task SearchAsync_SendsScopeAndQuery_AsJsonRequestBodyAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[]");

        // Act
        await this._client.SearchAsync("myapp", "myagent", "mythread", "alice&app_id=other", "hello world", CancellationToken.None);

        // Assert
        Assert.Single(this._handler.Requests);
        var request = this._handler.Requests[0];
        Assert.Equal(HttpMethod.Post, request.RequestMessage.Method);
        Assert.Equal("/v1/memories/search/", request.RequestMessage.RequestUri!.AbsolutePath);

        // The request is sent as a JSON body, so the value is preserved as an opaque string
        // (default System.Text.Json encoding escapes '&' as \u0026, unlike the raw query string
        // built by ClearMemoryAsync, but no additional parameter is smuggled in either way).
        Assert.Contains("\"app_id\":\"myapp\"", request.RequestBody);
        Assert.Contains("\"agent_id\":\"myagent\"", request.RequestBody);
        Assert.Contains("\"run_id\":\"mythread\"", request.RequestBody);
        Assert.Contains("\"user_id\":\"alice\\u0026app_id=other\"", request.RequestBody);
        Assert.Contains("\"query\":\"hello world\"", request.RequestBody);
    }

    [Fact]
    public async Task SearchAsync_DefaultsQueryToEmptyString_WhenInputTextIsNullAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("[]");

        // Act
        await this._client.SearchAsync("myapp", null, null, null, null, CancellationToken.None);

        // Assert
        Assert.Contains("\"query\":\"\"", this._handler.Requests[0].RequestBody);
    }

    [Fact]
    public async Task SearchAsync_ReturnsMemoryStrings_FromJsonResponseAsync()
    {
        // Arrange
        this._handler.EnqueueJsonResponse("""
            [
                { "id": "1", "memory": "likes tea", "hash": "h1", "score": 0.9, "created_at": "2024-01-01T00:00:00Z", "user_id": "alice", "agent_id": "a1", "session_id": "s1" },
                { "id": "2", "memory": "likes coffee", "hash": "h2", "score": 0.8, "created_at": "2024-01-01T00:00:00Z", "user_id": "alice", "agent_id": "a1", "session_id": "s1" }
            ]
            """);

        // Act
        var results = await this._client.SearchAsync("myapp", null, null, "alice", "beverages", CancellationToken.None);

        // Assert
        Assert.Equal(["likes tea", "likes coffee"], results);
    }

    [Fact]
    public async Task SearchAsync_Throws_WhenServerReturnsErrorStatusAsync()
    {
        // Arrange
        this._handler.EnqueueEmptyResponse(HttpStatusCode.InternalServerError);

        // Act & Assert
        await Assert.ThrowsAsync<HttpRequestException>(() => this._client.SearchAsync("myapp", null, null, null, "query", CancellationToken.None));
    }

    #endregion

    #region CreateMemoryAsync Tests

    [Fact]
    public async Task CreateMemoryAsync_Throws_WhenAllScopeValuesMissingAsync()
    {
        // Act & Assert
        var ex = await Assert.ThrowsAsync<ArgumentException>(() => this._client.CreateMemoryAsync(null, null, null, null, "hello", "user", CancellationToken.None));
        Assert.StartsWith("At least one of applicationId, agentId, threadId, or userId must be provided.", ex.Message);
        Assert.Empty(this._handler.Requests);
    }

    [Fact]
    public async Task CreateMemoryAsync_SendsScopeAndMessage_AsJsonRequestBodyAsync()
    {
        // Arrange
        this._handler.EnqueueEmptyResponse(HttpStatusCode.OK);

        // Act
        await this._client.CreateMemoryAsync("myapp", "myagent", "mythread", "alice&app_id=other", "hello there", "User", CancellationToken.None);

        // Assert
        Assert.Single(this._handler.Requests);
        var request = this._handler.Requests[0];
        Assert.Equal(HttpMethod.Post, request.RequestMessage.Method);
        Assert.Equal("/v1/memories/", request.RequestMessage.RequestUri!.AbsolutePath);

        Assert.Contains("\"app_id\":\"myapp\"", request.RequestBody);
        Assert.Contains("\"agent_id\":\"myagent\"", request.RequestBody);
        Assert.Contains("\"run_id\":\"mythread\"", request.RequestBody);
        Assert.Contains("\"user_id\":\"alice\\u0026app_id=other\"", request.RequestBody);
        Assert.Contains("\"content\":\"hello there\"", request.RequestBody);

        // The message role is lower-cased before being sent.
        Assert.Contains("\"role\":\"user\"", request.RequestBody);
    }

    [Fact]
    public async Task CreateMemoryAsync_Throws_WhenServerReturnsErrorStatusAsync()
    {
        // Arrange
        this._handler.EnqueueEmptyResponse(HttpStatusCode.InternalServerError);

        // Act & Assert
        await Assert.ThrowsAsync<HttpRequestException>(() => this._client.CreateMemoryAsync("myapp", null, null, null, "hello", "user", CancellationToken.None));
    }

    #endregion

    public void Dispose()
    {
        if (!this._disposed)
        {
            this._httpClient.Dispose();
            this._handler.Dispose();
            this._disposed = true;
        }
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        private readonly Queue<HttpResponseMessage> _responses = new();

        public List<(HttpRequestMessage RequestMessage, string RequestBody)> Requests { get; } = [];

        protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
#if NET
            var requestBody = await (request.Content?.ReadAsStringAsync(cancellationToken) ?? Task.FromResult(string.Empty));
#else
            var requestBody = await (request.Content?.ReadAsStringAsync() ?? Task.FromResult(string.Empty));
#endif
            this.Requests.Add((request, requestBody));
            return this._responses.Count > 0 ? this._responses.Dequeue() : new HttpResponseMessage(HttpStatusCode.OK);
        }

        public void EnqueueJsonResponse(string json) =>
            this._responses.Enqueue(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(json, Encoding.UTF8, "application/json")
            });

        public void EnqueueEmptyResponse(HttpStatusCode statusCode) =>
            this._responses.Enqueue(new HttpResponseMessage(statusCode));
    }
}
