// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

/// <summary>
/// Unit tests for the <see cref="TypeSafeDecisionClient"/> class, using a stub handler in place of the network.
/// </summary>
public class TypeSafeDecisionClientTests
{
    private const string OkBody = """{ "model": "jev-1.13.0", "answers": { "q": { "type": "noul", "noul": 0.75 } }, "usage": { "input_tokens": 12, "output_tokens": 0 } }""";

    private static DecisionRequest Request()
    {
        using JsonDocument state = JsonDocument.Parse("\"some state\"");
        return new DecisionRequest(state.RootElement.Clone(), [new BinaryDecisionQuestion("q", "Is it?")]);
    }

    #region Constructor

    [Theory]
    [InlineData(null)]
    [InlineData("")]
    [InlineData("  ")]
    public void Constructor_BlankApiKey_Throws(string? apiKey)
    {
        Assert.ThrowsAny<ArgumentException>(() => new TypeSafeDecisionClient(apiKey!));
    }

    [Fact]
    public void Constructor_HttpNonLoopbackEndpoint_Throws()
    {
        Assert.Throws<ArgumentException>("options", () => new TypeSafeDecisionClient("k", new() { Endpoint = new Uri("http://example.com/v1/systemone") }));
    }

    [Fact]
    public void Constructor_Defaults_UseTypeSafeEndpointAndAlias()
    {
        using var client = new TypeSafeDecisionClient("k");

        Assert.Equal(new Uri(TypeSafeDecisionClientOptions.DefaultEndpoint), client.Endpoint);
        Assert.Equal(TypeSafeDecisionClientOptions.DefaultModelId, client.ModelId);
    }

    [Fact]
    public void Constructor_MarksFeatureUsage()
    {
        FeatureUsageAssert.Reset();

        using var client = new TypeSafeDecisionClient("k");

        FeatureUsageAssert.Marked((int)FeatureIndex.TypeSafe);
    }

    #endregion

    #region GetService

    [Fact]
    public void GetService_ReturnsSelfAndMetadata()
    {
        using var client = new TypeSafeDecisionClient("k", new() { ModelId = "jev-1.13.0" });

        Assert.Same(client, client.GetService(typeof(IDecisionClient)));
        Assert.Same(client, client.GetService(typeof(TypeSafeDecisionClient)));
        var metadata = Assert.IsType<DecisionClientMetadata>(client.GetService(typeof(DecisionClientMetadata)));
        Assert.Equal("typesafe", metadata.ProviderName);
        Assert.Equal("jev-1.13.0", metadata.DefaultModelId);
        Assert.Equal(client.Endpoint, metadata.ProviderUri);
        Assert.Null(client.GetService(typeof(string)));
        Assert.Null(client.GetService(typeof(IDecisionClient), "key"));
    }

    #endregion

    #region GetResponseAsync

    [Fact]
    public async Task GetResponseAsync_SendsBearerJsonPostToEndpointAsync()
    {
        HttpRequestMessage? sent = null;
        string? sentBody = null;
        using var handler = new StubHandler(async (request, ct) =>
        {
            sent = request;
            sentBody = await request.Content!.ReadAsStringAsync(ct);
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(OkBody) };
        });
        using var http = new HttpClient(handler);
        using var client = new TypeSafeDecisionClient("secret-key", new() { ModelId = "jev-1.13.0" }, http);

        DecisionResponse response = await client.GetResponseAsync(Request());

        Assert.NotNull(sent);
        Assert.Equal(HttpMethod.Post, sent!.Method);
        Assert.Equal(new Uri(TypeSafeDecisionClientOptions.DefaultEndpoint), sent.RequestUri);
        Assert.Equal("Bearer", sent.Headers.Authorization!.Scheme);
        Assert.Equal("secret-key", sent.Headers.Authorization.Parameter);
        Assert.Equal("application/json", sent.Content!.Headers.ContentType!.MediaType);
        using JsonDocument body = JsonDocument.Parse(sentBody!);
        Assert.Equal("jev-1.13.0", body.RootElement.GetProperty("model").GetString());
        Assert.Equal(0.75, Assert.IsType<BinaryDecisionAnswer>(response.Answers["q"]).TrueProbability, precision: 6);
        Assert.Equal("jev-1.13.0", response.ModelId);
    }

    [Fact]
    public async Task GetResponseAsync_OptionsModelId_OverridesDefaultAsync()
    {
        string? sentBody = null;
        using var handler = new StubHandler(async (request, ct) =>
        {
            sentBody = await request.Content!.ReadAsStringAsync(ct);
            return new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent(OkBody) };
        });
        using var http = new HttpClient(handler);
        using var client = new TypeSafeDecisionClient("k", httpClient: http);

        await client.GetResponseAsync(Request(), new DecisionOptions { ModelId = "jev-preview" });

        using JsonDocument body = JsonDocument.Parse(sentBody!);
        Assert.Equal("jev-preview", body.RootElement.GetProperty("model").GetString());
    }

    [Fact]
    public async Task GetResponseAsync_ProviderError_ThrowsClassifiedAndRedactedAsync()
    {
        using var handler = new StubHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.Unauthorized)
        {
            Content = new StringContent("{\"error\":\"bad key secret-key\"}"),
        }));
        using var http = new HttpClient(handler);
        using var client = new TypeSafeDecisionClient("secret-key", httpClient: http);

        var ex = await Assert.ThrowsAsync<DecisionClientException>(() => client.GetResponseAsync(Request()));

        Assert.Equal(DecisionFailureKind.Authentication, ex.Kind);
        Assert.Equal(401, ex.StatusCode);
        Assert.DoesNotContain("secret-key", ex.Message);
        Assert.Contains("[redacted]", ex.Message);
    }

    [Fact]
    public async Task GetResponseAsync_RateLimited_IsTransientAsync()
    {
        using var handler = new StubHandler((_, _) => Task.FromResult(new HttpResponseMessage((HttpStatusCode)429) { Content = new StringContent("slow down") }));
        using var http = new HttpClient(handler);
        using var client = new TypeSafeDecisionClient("k", httpClient: http);

        var ex = await Assert.ThrowsAsync<DecisionClientException>(() => client.GetResponseAsync(Request()));

        Assert.True(ex.IsTransient);
        Assert.Equal(DecisionFailureKind.RateLimited, ex.Kind);
    }

    [Fact]
    public async Task GetResponseAsync_NetworkFailure_ThrowsUnknownWithInnerAsync()
    {
        using var handler = new StubHandler((_, _) => throw new HttpRequestException("connection refused"));
        using var http = new HttpClient(handler);
        using var client = new TypeSafeDecisionClient("k", httpClient: http);

        var ex = await Assert.ThrowsAsync<DecisionClientException>(() => client.GetResponseAsync(Request()));

        Assert.Equal(DecisionFailureKind.Unknown, ex.Kind);
        Assert.IsType<HttpRequestException>(ex.InnerException);
    }

    [Fact]
    public async Task GetResponseAsync_CallerCancellation_PropagatesAsync()
    {
        using var cts = new CancellationTokenSource();
        using var handler = new StubHandler((_, ct) =>
        {
            cts.Cancel();
            ct.ThrowIfCancellationRequested();
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK));
        });
        using var http = new HttpClient(handler);
        using var client = new TypeSafeDecisionClient("k", httpClient: http);

        await Assert.ThrowsAnyAsync<OperationCanceledException>(() => client.GetResponseAsync(Request(), cancellationToken: cts.Token));
    }

    [Fact]
    public async Task GetResponseAsync_UnusableSuccessBody_ThrowsInvalidResponseAsync()
    {
        using var handler = new StubHandler((_, _) => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK) { Content = new StringContent("{\"model\":\"m\",\"answers\":{}}") }));
        using var http = new HttpClient(handler);
        using var client = new TypeSafeDecisionClient("k", httpClient: http);

        var ex = await Assert.ThrowsAsync<DecisionClientException>(() => client.GetResponseAsync(Request()));

        Assert.Equal(DecisionFailureKind.InvalidResponse, ex.Kind);
    }

    [Fact]
    public async Task GetResponseAsync_NullRequest_ThrowsAsync()
    {
        using var client = new TypeSafeDecisionClient("k");

        await Assert.ThrowsAsync<ArgumentNullException>("request", () => client.GetResponseAsync(null!));
    }

    #endregion

    private sealed class StubHandler(Func<HttpRequestMessage, CancellationToken, Task<HttpResponseMessage>> send) : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken) => send(request, cancellationToken);
    }
}
