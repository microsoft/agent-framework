// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Responses;

#pragma warning disable OPENAI001, SCME0001, SCME0002, MEAI001

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Verifies that <see cref="UserAgentResponsesClient"/> preserves user-supplied client options
/// (Transport, RetryPolicy, UserAgentApplicationId, OrganizationId, ProjectId) and adds the
/// hosted-agent User-Agent supplement on every outgoing request, including streaming.
/// Covers both the Azure-flavored <see cref="ProjectResponsesClient"/> and the native OpenAI
/// <see cref="ResponsesClient"/>.
/// </summary>
public sealed partial class UserAgentResponsesClientTests
{
    private const string TestEndpoint = "https://fake-foundry.example.com/api/projects/fake-prj";
    private const string OpenAIEndpoint = "https://fake-openai.example.com/v1";
    private const string Deployment = "fake-deployment";

    [System.Text.RegularExpressions.GeneratedRegex("foundry-hosting/agent-framework-dotnet")]
    private static partial System.Text.RegularExpressions.Regex SupplementRegex();

    [Fact]
    public async Task Polyfill_NonStreaming_PreservesAppId_ThroughCustomTransport_AddsSupplementAsync()
    {
        // Arrange
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var inner = BuildInner(httpClient, userAgentApplicationId: "MY_APP_ID");
        var chat = MakeWithDelegating(inner);

        // Act
        _ = await chat.GetResponseAsync("hello");

        // Assert
        var req = Assert.Single(handler.Requests);
        Assert.Contains("MY_APP_ID", req.UserAgent);
        Assert.Contains("MEAI/", req.UserAgent);
        Assert.Contains("foundry-hosting/agent-framework-dotnet", req.UserAgent);
        Assert.StartsWith(TestEndpoint, req.Uri);
    }

    [Fact]
    public async Task Polyfill_Streaming_PreservesAppId_ThroughCustomTransport_AddsSupplementAsync()
    {
        // Arrange
        using var handler = new RecordingHandler(MinimalSseResponse());
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var inner = BuildInner(httpClient, userAgentApplicationId: "MY_APP_ID");
        var chat = MakeWithDelegating(inner);

        // Act
        await foreach (var _ in chat.GetStreamingResponseAsync("hello"))
        {
        }

        // Assert
        var req = Assert.Single(handler.Requests);
        Assert.Contains("MY_APP_ID", req.UserAgent);
        Assert.Contains("MEAI/", req.UserAgent);
        Assert.Contains("foundry-hosting/agent-framework-dotnet", req.UserAgent);
        Assert.StartsWith(TestEndpoint, req.Uri);
    }

    [Fact]
    public async Task Polyfill_PreservesOrganizationAndProjectHeadersAsync()
    {
        // Arrange
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var inner = BuildInner(httpClient,
            userAgentApplicationId: "MY_APP_ID",
            organizationId: "org_xyz",
            projectId: "proj_abc");
        var chat = MakeWithDelegating(inner);

        // Act
        _ = await chat.GetResponseAsync("hello");

        // Assert
        var req = Assert.Single(handler.Requests);
        Assert.Contains("MY_APP_ID", req.UserAgent);
        Assert.Contains("foundry-hosting/agent-framework-dotnet", req.UserAgent);
    }

    [Fact]
    public async Task Polyfill_HonorsUserSuppliedRetryPolicy_ByCountingRetriesAsync()
    {
        // Arrange
        var retryPolicy = new CountingRetryPolicy(extraAttempts: 2);
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var inner = BuildInner(httpClient, userAgentApplicationId: "MY_APP_ID", retryPolicy: retryPolicy);
        var chat = MakeWithDelegating(inner);

        // Act
        _ = await chat.GetResponseAsync("hello");

        // Assert: retry policy ran (1 + 2 extras = 3 attempts).
        Assert.Equal(3, handler.Requests.Count);
        Assert.Equal(3, retryPolicy.InvocationCount);
        foreach (var req in handler.Requests)
        {
            Assert.Contains("MY_APP_ID", req.UserAgent);
            Assert.Contains("MEAI/", req.UserAgent);
            Assert.Contains("foundry-hosting/agent-framework-dotnet", req.UserAgent);
        }
    }

    [Fact]
    public async Task Baseline_NonStreaming_DoesNotInjectSupplementAsync()
    {
        // Arrange
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var inner = BuildInner(httpClient, userAgentApplicationId: "MY_APP_ID");
        var chat = inner.AsIChatClient(Deployment);

        // Act
        _ = await chat.GetResponseAsync("hello");

        // Assert
        var req = Assert.Single(handler.Requests);
        Assert.Contains("MY_APP_ID", req.UserAgent);
        Assert.Contains("MEAI/", req.UserAgent);
        Assert.DoesNotContain("foundry-hosting/agent-framework-dotnet", req.UserAgent);
    }

    [Fact]
    public async Task Polyfill_NativeOpenAIResponsesClient_NonStreaming_AddsSupplementAsync()
    {
        // Arrange: use the NATIVE OpenAI SDK ResponsesClient (no Foundry / Azure project involved).
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var inner = BuildOpenAIInner(httpClient, userAgentApplicationId: "MY_APP_ID");
        var chat = MakeWithDelegating(inner);

        // Act
        _ = await chat.GetResponseAsync("hello");

        // Assert
        var req = Assert.Single(handler.Requests);
        Assert.Contains("MY_APP_ID", req.UserAgent);
        Assert.Contains("MEAI/", req.UserAgent);
        Assert.Contains("foundry-hosting/agent-framework-dotnet", req.UserAgent);
        Assert.StartsWith(OpenAIEndpoint, req.Uri);
    }

    [Fact]
    public async Task Polyfill_NativeOpenAIResponsesClient_Streaming_AddsSupplementAsync()
    {
        // Arrange
        using var handler = new RecordingHandler(MinimalSseResponse());
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var inner = BuildOpenAIInner(httpClient, userAgentApplicationId: "MY_APP_ID");
        var chat = MakeWithDelegating(inner);

        // Act
        await foreach (var _ in chat.GetStreamingResponseAsync("hello"))
        {
        }

        // Assert
        var req = Assert.Single(handler.Requests);
        Assert.Contains("MY_APP_ID", req.UserAgent);
        Assert.Contains("MEAI/", req.UserAgent);
        Assert.Contains("foundry-hosting/agent-framework-dotnet", req.UserAgent);
        Assert.StartsWith(OpenAIEndpoint, req.Uri);
    }

    [Theory]
    [InlineData("DeleteResponseAsync")]
    [InlineData("CancelResponseAsync")]
    [InlineData("GetInputTokenCountAsync")]
    [InlineData("CompactResponseAsync")]
    [InlineData("GetResponseInputItemCollectionPageAsync")]
    public async Task Polyfill_AncillaryProtocolMethod_AddsSupplementAsync(string method)
    {
        // Arrange: hit the wrapper DIRECTLY (no MEAI in the chain) to simulate user code that
        // grabs the underlying ResponsesClient via chat.GetService<ResponsesClient>() and invokes
        // a non-Create/Get protocol method. This is the regression path: without overriding these,
        // the wrapper's dummy throwing pipeline would fire.
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var inner = BuildOpenAIInner(httpClient, userAgentApplicationId: "MY_APP_ID");
        var wrapper = new UserAgentResponsesClient(inner);

        // Act
        switch (method)
        {
            case "DeleteResponseAsync":
                _ = await wrapper.DeleteResponseAsync("resp_1", options: null!);
                break;
            case "CancelResponseAsync":
                _ = await wrapper.CancelResponseAsync("resp_1", options: null!);
                break;
            case "GetInputTokenCountAsync":
                _ = await wrapper.GetInputTokenCountAsync("application/json", BinaryContent.Create(BinaryData.FromString("{}")));
                break;
            case "CompactResponseAsync":
                _ = await wrapper.CompactResponseAsync("application/json", BinaryContent.Create(BinaryData.FromString("{}")));
                break;
            case "GetResponseInputItemCollectionPageAsync":
                _ = await wrapper.GetResponseInputItemCollectionPageAsync("resp_1", limit: null, order: "asc", after: "a", before: "b", options: null!);
                break;
            default:
                Assert.Fail($"Unhandled method: {method}");
                break;
        }

        // Assert
        var req = Assert.Single(handler.Requests);
        Assert.Contains("MY_APP_ID", req.UserAgent);
        Assert.Contains("foundry-hosting/agent-framework-dotnet", req.UserAgent);
    }

    [Fact]
    public async Task Polyfill_RetryWithinCall_DoesNotDuplicateSupplementInUserAgentAsync()
    {
        // Arrange: a custom retry policy that re-runs the inner pipeline on the SAME message,
        // so the per-call HostedAgentUserAgentPolicy fires multiple times against the same headers.
        // The policy's Contains-guard must prevent the supplement from appearing twice.
        var retryPolicy = new CountingRetryPolicy(extraAttempts: 2);
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var inner = BuildInner(httpClient, userAgentApplicationId: "MY_APP_ID", retryPolicy: retryPolicy);
        var chat = MakeWithDelegating(inner);

        // Act
        _ = await chat.GetResponseAsync("hello");

        // Assert: each retry attempt must have exactly ONE foundry-hosting segment, never two.
        Assert.Equal(3, handler.Requests.Count);
        foreach (var req in handler.Requests)
        {
            int matches = SupplementRegex().Matches(req.UserAgent).Count;
            Assert.True(matches == 1, $"Expected exactly one foundry-hosting segment per retry attempt, got {matches}. UA: {req.UserAgent}");
        }
    }

    [Fact]
    public async Task TryApplyUserAgent_CalledTwiceOnSameAgent_DoesNotDoubleWrapAsync()
    {
        // Arrange: build a real ChatClientAgent whose IChatClient resolves to MEAI's
        // OpenAIResponsesChatClient → ProjectResponsesClient (with a fake transport).
        using var handler = new RecordingHandler(MinimalResponseJson());
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler);
#pragma warning restore CA5399
        var inner = BuildInner(httpClient, userAgentApplicationId: "MY_APP_ID");
        IChatClient chatClient = inner.AsIChatClient(Deployment);
        AIAgent agent = new ChatClientAgent(chatClient);

        // Act: apply twice.
        FoundryHostingExtensions.TryApplyUserAgent(agent);
        FoundryHostingExtensions.TryApplyUserAgent(agent);

        // Assert: invoking the agent produces exactly ONE outbound request whose UA contains
        // the supplement EXACTLY ONCE (would be twice if the wrapper were nested).
        _ = await chatClient.GetResponseAsync("hello");
        var req = Assert.Single(handler.Requests);
        int matches = SupplementRegex().Matches(req.UserAgent).Count;
        Assert.True(matches == 1, $"Expected exactly one foundry-hosting segment, got {matches}. UA: {req.UserAgent}");
    }

    [Fact]
    public void OpenAIResponsesChatClient_ResponseClientField_ReflectionGuard()
    {
        // Guards the polyfill's reflection target. Failure here means MEAI internals
        // changed and the polyfill needs updating.
        var meaiType = typeof(MicrosoftExtensionsAIResponsesExtensions).Assembly
            .GetType("Microsoft.Extensions.AI.OpenAIResponsesChatClient");
        Assert.NotNull(meaiType);

        var field = meaiType!.GetField("_responseClient", BindingFlags.NonPublic | BindingFlags.Instance);
        Assert.NotNull(field);
        Assert.True(typeof(ResponsesClient).IsAssignableFrom(field!.FieldType),
            $"Expected _responseClient to be assignable to ResponsesClient but was {field.FieldType}.");
    }

    [Fact]
    public void ResponsesClient_PipelineProperty_ReflectionGuard()
    {
        // The polyfill design assumes ResponsesClient.Pipeline remains accessible.
        var pipelineProp = typeof(ResponsesClient).GetProperty("Pipeline", BindingFlags.Public | BindingFlags.Instance);
        Assert.NotNull(pipelineProp);
        Assert.Equal(typeof(ClientPipeline), pipelineProp!.PropertyType);
    }

    private static IChatClient MakeWithDelegating(ResponsesClient inner)
    {
        IChatClient meai = inner.AsIChatClient(Deployment);
        var meaiType = meai.GetType();
        var field = meaiType.GetField("_responseClient", BindingFlags.NonPublic | BindingFlags.Instance)!;
        field.SetValue(meai, new UserAgentResponsesClient(inner));
        return meai;
    }

    private static ProjectResponsesClient BuildInner(
        HttpClient httpClient,
        string? userAgentApplicationId = null,
        string? organizationId = null,
        string? projectId = null,
        PipelinePolicy? retryPolicy = null)
    {
        var options = new ProjectResponsesClientOptions
        {
            Transport = new HttpClientPipelineTransport(httpClient),
        };
        if (userAgentApplicationId is not null)
        {
            options.UserAgentApplicationId = userAgentApplicationId;
        }
        if (organizationId is not null)
        {
            options.OrganizationId = organizationId;
        }
        if (projectId is not null)
        {
            options.ProjectId = projectId;
        }
        if (retryPolicy is not null)
        {
            options.RetryPolicy = retryPolicy;
        }

        return new ProjectResponsesClient(new Uri(TestEndpoint), new FakeAuthenticationTokenProvider(), options);
    }

    private static ResponsesClient BuildOpenAIInner(
        HttpClient httpClient,
        string? userAgentApplicationId = null)
    {
        var options = new OpenAIClientOptions
        {
            Transport = new HttpClientPipelineTransport(httpClient),
            Endpoint = new Uri(OpenAIEndpoint),
        };
        if (userAgentApplicationId is not null)
        {
            options.UserAgentApplicationId = userAgentApplicationId;
        }

        return new ResponsesClient(new ApiKeyCredential("test-key"), options);
    }

    private static string MinimalResponseJson() => """
        {
          "id":"resp_1","object":"response","created_at":1700000000,"status":"completed",
          "model":"fake","output":[],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}
        }
        """;

    private static string MinimalSseResponse()
    {
        var sb = new StringBuilder();
        sb.Append("event: response.completed\n");
        sb.Append("data: ").Append("""{"type":"response.completed","response":{"id":"resp_1","object":"response","created_at":1700000000,"status":"completed","model":"fake","output":[],"usage":{"input_tokens":1,"output_tokens":1,"total_tokens":2}}}""").Append("\n\n");
        sb.Append("data: [DONE]\n\n");
        return sb.ToString();
    }

    private sealed class RecordingHandler : HttpClientHandler
    {
        private readonly string _body;
        public List<RecordedRequest> Requests { get; } = [];

        public RecordingHandler(string body)
        {
            this._body = body;
        }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            string ua = request.Headers.TryGetValues("User-Agent", out var values)
                ? string.Join(",", values)
                : "(none)";
            this.Requests.Add(new RecordedRequest(request.Method.Method, request.RequestUri?.ToString() ?? "?", ua));

            var resp = new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(this._body, Encoding.UTF8, "application/json"),
                RequestMessage = request,
            };
            return Task.FromResult(resp);
        }
    }

    private readonly record struct RecordedRequest(string Method, string Uri, string UserAgent);

    private sealed class CountingRetryPolicy : PipelinePolicy
    {
        private readonly int _extraAttempts;
        public int InvocationCount { get; private set; }

        public CountingRetryPolicy(int extraAttempts)
        {
            this._extraAttempts = extraAttempts;
        }

        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            for (int i = 0; i <= this._extraAttempts; i++)
            {
                this.InvocationCount++;
                ProcessNext(message, pipeline, currentIndex);
            }
        }

        public override async ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            for (int i = 0; i <= this._extraAttempts; i++)
            {
                this.InvocationCount++;
                await ProcessNextAsync(message, pipeline, currentIndex).ConfigureAwait(false);
            }
        }
    }
}
