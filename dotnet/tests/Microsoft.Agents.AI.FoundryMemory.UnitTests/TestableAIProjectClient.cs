// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Projects;
using Azure.Core;

namespace Microsoft.Agents.AI.FoundryMemory.UnitTests;

/// <summary>
/// Creates a testable AIProjectClient with a mock HTTP handler.
/// </summary>
internal sealed class TestableAIProjectClient : IDisposable
{
    private readonly HttpClient _httpClient;

    public TestableAIProjectClient(
        string? searchMemoriesResponse = null,
        string? updateMemoriesResponse = null,
        HttpStatusCode? searchStatusCode = null,
        HttpStatusCode? updateStatusCode = null,
        HttpStatusCode? deleteStatusCode = null,
        HttpStatusCode? createStoreStatusCode = null,
        HttpStatusCode? getStoreStatusCode = null)
    {
        this.Handler = new MockHttpMessageHandler(
            searchMemoriesResponse,
            updateMemoriesResponse,
            searchStatusCode,
            updateStatusCode,
            deleteStatusCode,
            createStoreStatusCode,
            getStoreStatusCode);

        this._httpClient = new HttpClient(this.Handler);

        AIProjectClientOptions options = new()
        {
            Transport = new HttpClientPipelineTransport(this._httpClient)
        };

        // Using a valid format endpoint
        this.Client = new AIProjectClient(
            new Uri("https://test.services.ai.azure.com/api/projects/test-project"),
            new MockTokenCredential(),
            options);
    }

    public AIProjectClient Client { get; }

    public MockHttpMessageHandler Handler { get; }

    public void Dispose()
    {
        this._httpClient.Dispose();
        this.Handler.Dispose();
    }
}

/// <summary>
/// Mock HTTP message handler for testing.
/// </summary>
internal sealed class MockHttpMessageHandler : HttpMessageHandler
{
    private readonly string? _searchMemoriesResponse;
    private readonly string? _updateMemoriesResponse;
    private readonly HttpStatusCode _searchStatusCode;
    private readonly HttpStatusCode _updateStatusCode;
    private readonly HttpStatusCode _deleteStatusCode;
    private readonly HttpStatusCode _createStoreStatusCode;
    private readonly HttpStatusCode _getStoreStatusCode;

    public MockHttpMessageHandler(
        string? searchMemoriesResponse = null,
        string? updateMemoriesResponse = null,
        HttpStatusCode? searchStatusCode = null,
        HttpStatusCode? updateStatusCode = null,
        HttpStatusCode? deleteStatusCode = null,
        HttpStatusCode? createStoreStatusCode = null,
        HttpStatusCode? getStoreStatusCode = null)
    {
        this._searchMemoriesResponse = searchMemoriesResponse ?? """{"memories":[]}""";
        this._updateMemoriesResponse = updateMemoriesResponse ?? """{"update_id":"test-update-id","status":"queued"}""";
        this._searchStatusCode = searchStatusCode ?? HttpStatusCode.OK;
        this._updateStatusCode = updateStatusCode ?? HttpStatusCode.OK;
        this._deleteStatusCode = deleteStatusCode ?? HttpStatusCode.NoContent;
        this._createStoreStatusCode = createStoreStatusCode ?? HttpStatusCode.Created;
        this._getStoreStatusCode = getStoreStatusCode ?? HttpStatusCode.NotFound;
    }

    public string? LastRequestUri { get; private set; }
    public string? LastRequestBody { get; private set; }
    public HttpMethod? LastRequestMethod { get; private set; }

    protected override async Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
    {
        this.LastRequestUri = request.RequestUri?.ToString();
        this.LastRequestMethod = request.Method;

        if (request.Content != null)
        {
#if NET472
            this.LastRequestBody = await request.Content.ReadAsStringAsync().ConfigureAwait(false);
#else
            this.LastRequestBody = await request.Content.ReadAsStringAsync(cancellationToken).ConfigureAwait(false);
#endif
        }

        string path = request.RequestUri?.AbsolutePath ?? "";

        // Route based on path and method
        if (path.Contains("/memory-stores/") && path.Contains("/search") && request.Method == HttpMethod.Post)
        {
            return CreateResponse(this._searchStatusCode, this._searchMemoriesResponse);
        }

        if (path.Contains("/memory-stores/") && path.Contains("/memories") && request.Method == HttpMethod.Post)
        {
            return CreateResponse(this._updateStatusCode, this._updateMemoriesResponse);
        }

        if (path.Contains("/memory-stores/") && path.Contains("/scopes") && request.Method == HttpMethod.Delete)
        {
            return CreateResponse(this._deleteStatusCode, "");
        }

        if (path.Contains("/memory-stores") && request.Method == HttpMethod.Post)
        {
            return CreateResponse(this._createStoreStatusCode, """{"name":"test-store","status":"active"}""");
        }

        if (path.Contains("/memory-stores/") && request.Method == HttpMethod.Get)
        {
            return CreateResponse(this._getStoreStatusCode, """{"name":"test-store","status":"active"}""");
        }

        // Default response
        return CreateResponse(HttpStatusCode.NotFound, "{}");
    }

    private static HttpResponseMessage CreateResponse(HttpStatusCode statusCode, string? content)
    {
        return new HttpResponseMessage(statusCode)
        {
            Content = new StringContent(content ?? "{}", Encoding.UTF8, "application/json")
        };
    }
}

/// <summary>
/// Mock token credential for testing.
/// </summary>
internal sealed class MockTokenCredential : TokenCredential
{
    public override AccessToken GetToken(TokenRequestContext requestContext, CancellationToken cancellationToken)
    {
        return new AccessToken("mock-token", DateTimeOffset.UtcNow.AddHours(1));
    }

    public override ValueTask<AccessToken> GetTokenAsync(TokenRequestContext requestContext, CancellationToken cancellationToken)
    {
        return new ValueTask<AccessToken>(new AccessToken("mock-token", DateTimeOffset.UtcNow.AddHours(1)));
    }
}

/// <summary>
/// Source-generated JSON serializer context for unit test types.
/// </summary>
[JsonSourceGenerationOptions(PropertyNamingPolicy = JsonKnownNamingPolicy.CamelCase)]
[JsonSerializable(typeof(TestState))]
[JsonSerializable(typeof(TestScope))]
internal sealed partial class TestJsonContext : JsonSerializerContext
{
}

/// <summary>
/// Test state class for deserialization tests.
/// </summary>
internal sealed class TestState
{
    public TestScope? Scope { get; set; }
}

/// <summary>
/// Test scope class for deserialization tests.
/// </summary>
internal sealed class TestScope
{
    public string? Scope { get; set; }
}
