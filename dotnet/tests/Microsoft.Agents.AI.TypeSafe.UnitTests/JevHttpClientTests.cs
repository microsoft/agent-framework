// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.TypeSafe.UnitTests;

public sealed class JevHttpClientTests
{
    private const string ApiKey = "test-key-9f2c";

    [Fact]
    public async Task InvokeAsync_PostsTheWireRequestAndReturnsTheResponseAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        AIFunction tool = CreateBuilder(httpClient).Build();

        // Act
        object? result = await tool.InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert
        JevTestHttpHandler.CapturedRequest request = Assert.Single(handler.Requests);
        Assert.Equal(HttpMethod.Post, request.Method);
        Assert.Equal(new Uri("https://api.typesafe.ai/v1/systemone"), request.Uri);
        Assert.Equal("Bearer", request.Authorization!.Scheme);
        Assert.Equal(ApiKey, request.Authorization.Parameter);

        JsonObject expected = JsonNode.Parse(JevTestData.RequestJson)!.AsObject();
        expected["model"] = "jev-latest";
        Assert.True(JsonNode.DeepEquals(expected, JsonNode.Parse(request.Body)), request.Body);

        JsonElement json = Assert.IsType<JsonElement>(result);
        Assert.True(JsonNode.DeepEquals(JsonNode.Parse(JevTestData.ResponseJson), JsonNode.Parse(json.GetRawText())), json.GetRawText());
    }

    [Fact]
    public async Task InvokeAsync_CustomModelAndEndpoint_AreUsedAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        var options = new JevAIToolOptions { ModelId = "jev-1.13", Endpoint = new Uri("https://proxy.contoso.com/jev") };

        // Act
        await CreateBuilder(httpClient, options).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert
        JevTestHttpHandler.CapturedRequest request = Assert.Single(handler.Requests);
        Assert.Equal(new Uri("https://proxy.contoso.com/jev"), request.Uri);
        Assert.Equal("jev-1.13", (string?)JsonNode.Parse(request.Body)!["model"]);
    }

    [Fact]
    public async Task InvokeAsync_CustomPolicy_RunsInThePipelineAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        var options = new JevAIToolOptions();
        options.AddPolicy(new HeaderPolicy("x-tenant", "contoso"), PipelinePosition.PerCall);

        // Act
        await CreateBuilder(httpClient, options).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert
        Assert.Equal("contoso", Assert.Single(handler.Requests).Headers["x-tenant"]);
    }

    [Fact]
    public async Task InvokeAsync_RateLimitedOrOverloaded_RetriesWithBackoffAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler()
            .Reply(HttpStatusCode.TooManyRequests, "{}")
            .Reply((HttpStatusCode)529, "{}")
            .Reply(HttpStatusCode.OK, JevTestData.ResponseJson);
        using var httpClient = new HttpClient(handler);
        List<TimeSpan> waits = [];

        // Act
        object? result = await CreateBuilder(httpClient, waits: waits).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert: the SDK backoff is 500 ms doubled per attempt, minus up to 25% jitter.
        Assert.Equal(3, handler.Requests.Count);
        Assert.Equal(2, waits.Count);
        Assert.InRange(waits[0], TimeSpan.FromMilliseconds(375), TimeSpan.FromMilliseconds(500));
        Assert.InRange(waits[1], TimeSpan.FromMilliseconds(750), TimeSpan.FromMilliseconds(1000));
        Assert.Equal("technical", Assert.IsType<JsonElement>(result).GetProperty("answers").GetProperty("department").GetProperty("choice").GetString());
    }

    [Theory]
    [InlineData(503)]
    [InlineData(520)]
    [InlineData(408)]
    public async Task InvokeAsync_TransientStatus_IsRetriedLikeTheSdkAsync(int status)
    {
        // Arrange
        using var handler = new JevTestHttpHandler()
            .Reply((HttpStatusCode)status, "{}")
            .Reply(HttpStatusCode.OK, JevTestData.ResponseJson);
        using var httpClient = new HttpClient(handler);

        // Act
        await CreateBuilder(httpClient).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert
        Assert.Equal(2, handler.Requests.Count);
    }

    [Fact]
    public async Task InvokeAsync_StillRateLimitedAfterRetries_FailsWithTheStatusAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.TooManyRequests, """{"detail":"Rate limit exceeded"}""");
        using var httpClient = new HttpClient(handler);

        // Act
        ClientResultException exception = await Assert.ThrowsAsync<ClientResultException>(() =>
            CreateBuilder(httpClient).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson)).AsTask());

        // Assert: the first attempt plus the SDK's two retries.
        Assert.Equal(429, exception.Status);
        Assert.Equal(3, handler.Requests.Count);
    }

    [Fact]
    public async Task InvokeAsync_RetryAfterSeconds_IsWaitedAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler()
            .Reply(HttpStatusCode.TooManyRequests, "{}", new RetryConditionHeaderValue(TimeSpan.FromSeconds(5)))
            .Reply(HttpStatusCode.OK, JevTestData.ResponseJson);
        using var httpClient = new HttpClient(handler);
        List<TimeSpan> waits = [];

        // Act
        await CreateBuilder(httpClient, waits: waits).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert
        Assert.Equal(2, handler.Requests.Count);
        Assert.Equal(TimeSpan.FromSeconds(5), Assert.Single(waits));
    }

    [Fact]
    public async Task InvokeAsync_RetryAfterMilliseconds_IsPreferredAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler()
            .Reply(HttpStatusCode.TooManyRequests, "{}", new RetryConditionHeaderValue(TimeSpan.FromSeconds(30)), retryAfterMs: "1500")
            .Reply(HttpStatusCode.OK, JevTestData.ResponseJson);
        using var httpClient = new HttpClient(handler);
        List<TimeSpan> waits = [];

        // Act
        await CreateBuilder(httpClient, waits: waits).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert
        Assert.Equal(TimeSpan.FromMilliseconds(1500), Assert.Single(waits));
    }

    [Fact]
    public async Task InvokeAsync_RetryAfterDate_IsWaitedAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler()
            .Reply((HttpStatusCode)529, "{}", new RetryConditionHeaderValue(DateTimeOffset.UtcNow.AddSeconds(20)))
            .Reply(HttpStatusCode.OK, JevTestData.ResponseJson);
        using var httpClient = new HttpClient(handler);
        List<TimeSpan> waits = [];

        // Act
        await CreateBuilder(httpClient, waits: waits).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert
        Assert.Equal(2, handler.Requests.Count);
        Assert.InRange(Assert.Single(waits), TimeSpan.FromSeconds(15), TimeSpan.FromSeconds(21));
    }

    [Theory]
    [InlineData("Retry-After", "1e300")]
    [InlineData("Retry-After", "99999999999999")]
    [InlineData("Retry-After", "NaN")]
    [InlineData("retry-after-ms", "1e30")]
    [InlineData("retry-after-ms", "NaN")]
    public async Task InvokeAsync_MalformedOrHugeServerDelay_FallsBackToBackoffAsync(string header, string value)
    {
        // Arrange
        using var handler = new JevTestHttpHandler()
            .Reply(
                HttpStatusCode.TooManyRequests,
                "{}",
                retryAfterMs: header == "retry-after-ms" ? value : null,
                retryAfterRaw: header == "Retry-After" ? value : null)
            .Reply(HttpStatusCode.OK, JevTestData.ResponseJson);
        using var httpClient = new HttpClient(handler);
        List<TimeSpan> waits = [];

        // Act
        await CreateBuilder(httpClient, waits: waits).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert: like the SDK, an unusable server delay is ignored instead of failing the call.
        Assert.Equal(2, handler.Requests.Count);
        Assert.InRange(Assert.Single(waits), TimeSpan.FromMilliseconds(375), TimeSpan.FromMilliseconds(500));
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task InvokeAsync_RetryAfterBeyondTheLimit_FallsBackToBackoffAsync(bool asDate)
    {
        // Arrange
        RetryConditionHeaderValue retryAfter = asDate
            ? new RetryConditionHeaderValue(DateTimeOffset.UtcNow.AddHours(1))
            : new RetryConditionHeaderValue(TimeSpan.FromHours(1));
        using var handler = new JevTestHttpHandler()
            .Reply(HttpStatusCode.TooManyRequests, """{"detail":"Slow down"}""", retryAfter)
            .Reply(HttpStatusCode.OK, JevTestData.ResponseJson);
        using var httpClient = new HttpClient(handler);
        List<TimeSpan> waits = [];

        // Act
        await CreateBuilder(httpClient, waits: waits).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson));

        // Assert: waiting an hour would block the agent run, so the SDK's backoff is used instead.
        Assert.Equal(2, handler.Requests.Count);
        Assert.InRange(Assert.Single(waits), TimeSpan.FromMilliseconds(375), TimeSpan.FromMilliseconds(500));
    }

    [Fact]
    public async Task InvokeAsync_ReplacedRetryPolicy_IsUsedAndStillRetriesOverloadedAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler()
            .Reply((HttpStatusCode)529, "{}")
            .Reply((HttpStatusCode)529, "{}");
        using var httpClient = new HttpClient(handler);
        var options = new JevAIToolOptions
        {
            Transport = new HttpClientPipelineTransport(httpClient),
            RetryPolicy = new NoWaitRetryPolicy(maxRetries: 1),
        };

        // Act
        ClientResultException exception = await Assert.ThrowsAsync<ClientResultException>(() =>
            new JevAIToolBuilder(new ApiKeyCredential(ApiKey), options).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson)).AsTask());

        // Assert
        Assert.Equal(529, exception.Status);
        Assert.Equal(2, handler.Requests.Count);
    }

    [Theory]
    [InlineData(HttpStatusCode.Unauthorized, """{"detail":"Invalid API key"}""", "Invalid API key")]
    [InlineData(HttpStatusCode.BadRequest, """{"detail":"Too many score levels. Must have at most 10 levels."}""", "Too many score levels")]
    [InlineData(HttpStatusCode.UnprocessableEntity, """{"detail":[{"loc":["body","questions"],"msg":"Dictionary should have at least 1 item"}]}""", "Dictionary should have at least 1 item")]
    public async Task InvokeAsync_ApiError_FailsWithTheDetailButNotTheKeyAsync(HttpStatusCode status, string body, string expectedMessage)
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(status, body);
        using var httpClient = new HttpClient(handler);

        // Act
        ClientResultException exception = await Assert.ThrowsAsync<ClientResultException>(() =>
            CreateBuilder(httpClient).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson)).AsTask());

        // Assert
        Assert.Equal((int)status, exception.Status);
        Assert.Contains(expectedMessage, exception.Message, StringComparison.Ordinal);
        Assert.DoesNotContain(ApiKey, exception.Message, StringComparison.Ordinal);
        Assert.Single(handler.Requests);
    }

    [Theory]
    [InlineData("choice", "\"confidence\": 0.78, ", "", "confidence")]
    [InlineData("unknown type", "\"type\": \"noul\", \"noul\": 0.97", "\"type\": \"rank\", \"noul\": 0.97", "could not be read")]
    [InlineData("not json", "{", "<html>", "could not be read")]
    public async Task InvokeAsync_UnreadableResponse_FailsAsync(string scenario, string find, string replace, string expectedMessage)
    {
        // Arrange
        using var handler = new JevTestHttpHandler().Reply(HttpStatusCode.OK, ReplaceFirst(JevTestData.ResponseJson, find, replace));
        using var httpClient = new HttpClient(handler);

        // Act
        JsonException exception = await Assert.ThrowsAsync<JsonException>(() =>
            CreateBuilder(httpClient).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson)).AsTask());

        // Assert
        Assert.True(exception.Message.Contains(expectedMessage, StringComparison.Ordinal), $"{scenario}: {exception.Message}");
    }

    [Fact]
    public async Task InvokeAsync_Canceled_StopsWithoutSendingAsync()
    {
        // Arrange
        using var handler = new JevTestHttpHandler();
        using var httpClient = new HttpClient(handler);
        using var cancellation = new CancellationTokenSource();
        cancellation.Cancel();

        // Act & Assert
        await Assert.ThrowsAnyAsync<OperationCanceledException>(() =>
            CreateBuilder(httpClient).Build().InvokeAsync(JevTestData.Arguments(JevTestData.RequestJson), cancellation.Token).AsTask());
        Assert.Empty(handler.Requests);
    }

    private static JevAIToolBuilder CreateBuilder(HttpClient httpClient, JevAIToolOptions? options = null, List<TimeSpan>? waits = null)
    {
        options ??= new JevAIToolOptions();
        options.Transport = new HttpClientPipelineTransport(httpClient);
        options.RetryPolicy = new JevRetryPolicy { RecordedWaitsForTests = waits ?? [] };
        return new JevAIToolBuilder(new ApiKeyCredential(ApiKey), options);
    }

    private static string ReplaceFirst(string text, string find, string replace)
    {
        int index = text.IndexOf(find, StringComparison.Ordinal);
        Assert.True(index >= 0, $"'{find}' is not in the test response.");
        return string.Concat(text.AsSpan(0, index), replace, text.AsSpan(index + find.Length));
    }

    private sealed class HeaderPolicy(string name, string value) : PipelinePolicy
    {
        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set(name, value);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set(name, value);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }
    }

    private sealed class NoWaitRetryPolicy(int maxRetries) : ClientRetryPolicy(maxRetries)
    {
        protected override Task WaitAsync(TimeSpan time, CancellationToken cancellationToken) => Task.CompletedTask;

        protected override void Wait(TimeSpan time, CancellationToken cancellationToken)
        {
        }
    }
}
