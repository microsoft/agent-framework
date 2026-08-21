// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Concurrent;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Internal;
using Microsoft.Extensions.AI;

#pragma warning disable MEAI001

namespace Microsoft.Agents.AI.Foundry.UnitTests;

public sealed class FeatureUsageUserAgentPolicyTests
{
    [Theory]
    [InlineData("https://services.ai.azure.com/")]
    [InlineData("https://project.services.ai.azure.com/api/projects/test")]
    [InlineData("https://SERVICES.AI.AZURE.COM./")]
    [InlineData("https://inference.ai.azure.com/")]
    [InlineData("https://model.inference.ai.azure.com/models")]
    public void IsApprovedOrigin_AcceptsExactAndDotSubdomainHttpsFoundryOrigins(string value)
    {
        // Arrange / Act
        bool approved = FoundryUserAgentPolicies.Registration.IsApprovedOrigin(new Uri(value));

        // Assert
        Assert.True(approved);
    }

    [Theory]
    [InlineData("http://project.services.ai.azure.com/")]
    [InlineData("https://services.ai.azure.com.example.com/")]
    [InlineData("https://projectservices.ai.azure.com/")]
    [InlineData("https://evilservices.ai.azure.com/")]
    [InlineData("https://inference.ai.azure.com.evil.test/")]
    [InlineData("https://openai.azure.com/")]
    [InlineData("https://example.com/")]
    public void IsApprovedOrigin_RejectsHttpCustomLookalikeAndUnrelatedOrigins(string value)
    {
        // Arrange / Act
        bool approved = FoundryUserAgentPolicies.Registration.IsApprovedOrigin(new Uri(value));

        // Assert
        Assert.False(approved);
    }

    [Fact]
    public async Task Policy_RefreshesLiveTokenOnEveryEligibleRequestAsync()
    {
        // Arrange
        string? token = "v1.1";
        var policy = new FeatureUsageUserAgentPolicy(
            FoundryUserAgentPolicies.Registration.IsApprovedOrigin,
            (userAgent, includeFeatureToken) =>
                includeFeatureToken ? $"{userAgent.Split(' ')[0]} (feat={token})" : userAgent.Split(' ')[0]);
        var capturedUserAgents = new List<string?>();
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler, disposeHandler: false);
#pragma warning restore CA5399
        ClientPipeline pipeline = CreatePipeline(httpClient, policy, "app/1.0 (feat=v1.ff)", capturedUserAgents);

        // Act
        await SendAsync(pipeline, new Uri("https://project.services.ai.azure.com/first"));
        token = "v1.5";
        await SendAsync(pipeline, new Uri("https://project.services.ai.azure.com/second"));

        // Assert
        Assert.Equal(
            ["app/1.0 (feat=v1.1)", "app/1.0 (feat=v1.5)"],
            capturedUserAgents);
    }

    [Fact]
    public async Task Policy_EmptyToken_PreservesBaseHeaderByteForByteAsync()
    {
        // Arrange
        const string BaseHeader = "vendor/2.0  app/1.0 (custom=value)";
        var policy = new FeatureUsageUserAgentPolicy(
            FoundryUserAgentPolicies.Registration.IsApprovedOrigin,
            static (userAgent, _) => userAgent);
        var capturedUserAgents = new List<string?>();
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler, disposeHandler: false);
#pragma warning restore CA5399
        ClientPipeline pipeline = CreatePipeline(httpClient, policy, BaseHeader, capturedUserAgents);

        // Act
        await SendAsync(pipeline, new Uri("https://project.services.ai.azure.com/"));

        // Assert
        Assert.Equal(BaseHeader, Assert.Single(capturedUserAgents));
    }

    [Fact]
    public async Task Policy_IneligibleOrigin_RemovesStaleCommentWithoutChangingBaseHeaderAsync()
    {
        // Arrange
        var policy = new FeatureUsageUserAgentPolicy(
            FoundryUserAgentPolicies.Registration.IsApprovedOrigin,
            static (userAgent, includeFeatureToken) =>
                includeFeatureToken ? userAgent : userAgent.Replace(" (feat=v1.1)", string.Empty));
        var capturedUserAgents = new List<string?>();
        using var handler = new RecordingHandler();
#pragma warning disable CA5399
        using var httpClient = new HttpClient(handler, disposeHandler: false);
#pragma warning restore CA5399
        ClientPipeline pipeline = CreatePipeline(
            httpClient,
            policy,
            "vendor/2.0  app/1.0 (feat=v1.1)",
            capturedUserAgents);

        // Act
        await SendAsync(pipeline, new Uri("https://project.services.ai.azure.com.evil.test/"));

        // Assert
        Assert.Equal("vendor/2.0  app/1.0", Assert.Single(capturedUserAgents));
    }

    [Fact]
    public void Registration_UsesConditionalWeakTableToRegisterAtMostOnce()
    {
        // Arrange
        var policies = new OpenAIRequestPolicies();

        // Act
        bool first = FoundryUserAgentPolicies.Registration.TryRegister(policies);
        bool second = FoundryUserAgentPolicies.Registration.TryRegister(policies);

        // Assert
        Assert.True(first);
        Assert.False(second);
        Assert.Equal(2, EntriesCount(policies));
    }

    [Fact]
    public void Registration_IsAtMostOnceUnderConcurrency()
    {
        // Arrange
        var policies = new OpenAIRequestPolicies();
        var results = new ConcurrentBag<bool>();

        // Act
        Parallel.For(0, 32, _ => results.Add(FoundryUserAgentPolicies.Registration.TryRegister(policies)));

        // Assert
        Assert.Equal(1, results.Count(static added => added));
        Assert.Equal(2, EntriesCount(policies));
    }

    private static ClientPipeline CreatePipeline(
        HttpClient httpClient,
        FeatureUsageUserAgentPolicy policy,
        string userAgent,
        List<string?> capturedUserAgents)
    {
        return ClientPipeline.Create(
            new ClientPipelineOptions { Transport = new HttpClientPipelineTransport(httpClient) },
            perCallPolicies: [new SeedUserAgentPolicy(userAgent)],
            perTryPolicies: default,
            beforeTransportPolicies: [policy, new CaptureUserAgentPolicy(capturedUserAgents)]);
    }

    private static async Task SendAsync(ClientPipeline pipeline, Uri uri)
    {
        PipelineMessage message = pipeline.CreateMessage();
        message.Request.Method = "GET";
        message.Request.Uri = uri;
        await pipeline.SendAsync(message);
    }

    private static int EntriesCount(OpenAIRequestPolicies policies)
    {
        FieldInfo? field = typeof(OpenAIRequestPolicies).GetField("_entries", BindingFlags.Instance | BindingFlags.NonPublic);
        Assert.NotNull(field);
        return ((Array)field.GetValue(policies)!).Length;
    }

    private sealed class SeedUserAgentPolicy(string value) : PipelinePolicy
    {
        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set("User-Agent", value);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            message.Request.Headers.Set("User-Agent", value);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }
    }

    private sealed class CaptureUserAgentPolicy(List<string?> capturedUserAgents) : PipelinePolicy
    {
        public override void Process(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            _ = message.Request.Headers.TryGetValue("User-Agent", out string? userAgent);
            capturedUserAgents.Add(userAgent);
            ProcessNext(message, pipeline, currentIndex);
        }

        public override ValueTask ProcessAsync(PipelineMessage message, IReadOnlyList<PipelinePolicy> pipeline, int currentIndex)
        {
            _ = message.Request.Headers.TryGetValue("User-Agent", out string? userAgent);
            capturedUserAgents.Add(userAgent);
            return ProcessNextAsync(message, pipeline, currentIndex);
        }
    }

    private sealed class RecordingHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, CancellationToken cancellationToken)
        {
            return Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("{}", Encoding.UTF8, "application/json"),
                RequestMessage = request,
            });
        }
    }
}

#pragma warning restore MEAI001
