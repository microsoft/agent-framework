// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Azure.AI.OpenAI;
using Microsoft.Extensions.AI;
using OpenAI.Chat;
using OpenAI.Responses;

#pragma warning disable MEAI001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

/// <summary>
/// Executable probes documenting the System.ClientModel policy behavior Stage 1 can rely on.
/// </summary>
public sealed class PolicyPipelineInvestigationTests
{
    [Fact]
    public async Task PipelinePositions_PerCallRunsOnce_PerTryAndBeforeTransportRunForEveryRetry_InOrderAsync()
    {
        // Arrange
        var events = new List<string>();
        using var handler = new RetryOnceHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler, disposeHandler: false);
#pragma warning restore CA5399
        var options = new ClientPipelineOptions
        {
            RetryPolicy = new ClientRetryPolicy(maxRetries: 1),
            Transport = new HttpClientPipelineTransport(httpClient),
        };
        ClientPipeline pipeline = ClientPipeline.Create(
            options,
            perCallPolicies: [new RecordingPolicy("call", events)],
            perTryPolicies: [new RecordingPolicy("try", events)],
            beforeTransportPolicies: [new RecordingPolicy("transport", events)]);

        // Act
        PipelineMessage message = pipeline.CreateMessage();
        message.Request.Method = "GET";
        message.Request.Uri = new Uri("https://example.test/retry");
        await pipeline.SendAsync(message);

        // Assert
        Assert.Equal(2, handler.Count);
        Assert.Equal(["call", "try", "transport", "try", "transport"], events);
    }

    private sealed class RecordingPolicy(string name, List<string> events) : PipelinePolicy
    {
        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            events.Add(name);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            events.Add(name);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }
    }

    private sealed class RetryOnceHandler : HttpMessageHandler
    {
        public int Count { get; private set; }

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this.Count++;
            return Task.FromResult(new HttpResponseMessage(
                this.Count == 1 ? HttpStatusCode.InternalServerError : HttpStatusCode.OK)
            {
                Content = new StringContent("{}", Encoding.UTF8, "application/json"),
                RequestMessage = request,
            });
        }
    }
}

/// <summary>
/// Executable probes for caller-owned Azure OpenAI clients wrapped by Microsoft.Extensions.AI.
/// </summary>
public sealed class AzureOpenAIRequestPoliciesInvestigationTests
{
    [Fact]
    public async Task CallerOwnedChatAndResponsesWrappers_HaveIsolatedPolicies_PreserveTransport_AndRunAfterBaseUserAgentAsync()
    {
        // Arrange
        using var handler = new AzureOpenAIRecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler, disposeHandler: false);
#pragma warning restore CA5399
        var options = new AzureOpenAIClientOptions
        {
            Transport = new HttpClientPipelineTransport(httpClient),
        };
        var azureClient = new AzureOpenAIClient(
            new Uri("https://resource.openai.azure.com/"),
            new ApiKeyCredential("test-key"),
            options);

        ChatClient callerOwnedChatClient = azureClient.GetChatClient("deployment");
        ResponsesClient callerOwnedResponsesClient = azureClient.GetResponsesClient();
        IChatClient chatWrapper = callerOwnedChatClient.AsIChatClient();
        IChatClient secondChatWrapper = callerOwnedChatClient.AsIChatClient();
        IChatClient responsesWrapper = callerOwnedResponsesClient.AsIChatClient("deployment");
        OpenAIRequestPolicies chatPolicies = Assert.IsType<OpenAIRequestPolicies>(chatWrapper.GetService<OpenAIRequestPolicies>());
        OpenAIRequestPolicies secondChatPolicies = Assert.IsType<OpenAIRequestPolicies>(
            secondChatWrapper.GetService<OpenAIRequestPolicies>());
        OpenAIRequestPolicies responsesPolicies = Assert.IsType<OpenAIRequestPolicies>(responsesWrapper.GetService<OpenAIRequestPolicies>());
        var probe = new UserAgentOrderingProbePolicy();
        chatPolicies.AddPolicy(probe, PipelinePosition.BeforeTransport);

        // Act
        await IgnoreResponseParsingFailureAsync(() => chatWrapper.GetResponseAsync("hi"));
        await IgnoreResponseParsingFailureAsync(() => secondChatWrapper.GetResponseAsync("hi"));
        await IgnoreResponseParsingFailureAsync(() => responsesWrapper.GetResponseAsync("hi"));

        // Assert
        Assert.NotSame(chatPolicies, secondChatPolicies);
        Assert.NotSame(chatPolicies, responsesPolicies);
        Assert.Equal(3, handler.Requests.Count);
        Assert.All(handler.Requests, static request => Assert.Equal("resource.openai.azure.com", request.Uri.Host));
        Assert.Contains(handler.Requests, static request => request.Marker == "chat-only");
        Assert.Equal(2, handler.Requests.Count(static request => request.Marker is null));
        Assert.Single(probe.ObservedUserAgents);
        Assert.Contains("azsdk-net-AI.OpenAI/", probe.ObservedUserAgents[0]);
        Assert.Contains("MEAI/", probe.ObservedUserAgents[0]);
    }

    [Fact]
    public async Task CallerOwnedAzureClient_PreservesActualAzureOpenAIAndLookalikeOriginsAsync()
    {
        // Arrange
        using var handler = new AzureOpenAIRecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler, disposeHandler: false);
#pragma warning restore CA5399

        IChatClient approved = CreateChatWrapper(
            new Uri("https://resource.openai.azure.com/"),
            httpClient);
        IChatClient lookalike = CreateChatWrapper(
            new Uri("https://resource.openai.azure.com.evil.test/"),
            httpClient);

        // Act
        await IgnoreResponseParsingFailureAsync(() => approved.GetResponseAsync("hi"));
        await IgnoreResponseParsingFailureAsync(() => lookalike.GetResponseAsync("hi"));

        // Assert
        Assert.Equal(2, handler.Requests.Count);
        Assert.Equal("resource.openai.azure.com", handler.Requests[0].Uri.Host);
        Assert.Equal("resource.openai.azure.com.evil.test", handler.Requests[1].Uri.Host);
        Assert.True(IsCandidateAzureOpenAIOrigin(handler.Requests[0].Uri));
        Assert.False(IsCandidateAzureOpenAIOrigin(handler.Requests[1].Uri));
    }

    private static IChatClient CreateChatWrapper(Uri endpoint, HttpClient httpClient)
    {
        var options = new AzureOpenAIClientOptions
        {
            Transport = new HttpClientPipelineTransport(httpClient),
        };
        return new AzureOpenAIClient(endpoint, new ApiKeyCredential("test-key"), options)
            .GetChatClient("deployment")
            .AsIChatClient();
    }

    private static bool IsCandidateAzureOpenAIOrigin(Uri uri)
    {
        string host = uri.IdnHost.TrimEnd('.');
        return string.Equals(uri.Scheme, Uri.UriSchemeHttps, StringComparison.OrdinalIgnoreCase) &&
            (string.Equals(host, "openai.azure.com", StringComparison.OrdinalIgnoreCase) ||
             host.EndsWith(".openai.azure.com", StringComparison.OrdinalIgnoreCase) ||
             string.Equals(host, "cognitiveservices.azure.com", StringComparison.OrdinalIgnoreCase) ||
             host.EndsWith(".cognitiveservices.azure.com", StringComparison.OrdinalIgnoreCase));
    }

    private static async Task IgnoreResponseParsingFailureAsync(Func<Task<ChatResponse>> operation)
    {
        try
        {
            await operation();
        }
        catch (Exception exception)
        {
            // The fake response body is intentionally not a valid service payload.
            _ = exception;
        }
    }

    private sealed class UserAgentOrderingProbePolicy : PipelinePolicy
    {
        public List<string> ObservedUserAgents { get; } = [];

        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            this.ObserveAndStamp(message);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            this.ObserveAndStamp(message);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }

        private void ObserveAndStamp(PipelineMessage message)
        {
            _ = message.Request.Headers.TryGetValue("User-Agent", out string? userAgent);
            this.ObservedUserAgents.Add(userAgent ?? string.Empty);
            message.Request.Headers.Set("x-policy-probe", "chat-only");
        }
    }

    private sealed class AzureOpenAIRecordingHandler : HttpMessageHandler
    {
        public List<RecordedRequest> Requests { get; } = [];

        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            this.Requests.Add(new RecordedRequest(
                request.RequestUri!,
                request.Headers.TryGetValues("x-policy-probe", out IEnumerable<string>? values)
                    ? values.Single()
                    : null));

            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{}", Encoding.UTF8, "application/json"),
                RequestMessage = request,
            });
        }
    }

    private sealed class RecordedRequest(Uri uri, string? marker)
    {
        public Uri Uri { get; } = uri;

        public string? Marker { get; } = marker;
    }
}

#pragma warning restore MEAI001
