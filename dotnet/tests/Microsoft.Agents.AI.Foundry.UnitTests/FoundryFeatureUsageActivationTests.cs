// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Collections.Generic;
using System.Globalization;
using System.Net;
using System.Net.Http;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using Azure.AI.Extensions.OpenAI;
using Azure.AI.Projects;
using Microsoft.Agents.AI.Foundry.UnitTests.Memory;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Foundry.UnitTests;

[CollectionDefinition("FoundryFeatureUsageActivation", DisableParallelization = true)]
public sealed class FoundryFeatureUsageActivationGroup;

[Collection("FoundryFeatureUsageActivation")]
public sealed class FoundryFeatureUsageActivationTests : IDisposable
{
    public FoundryFeatureUsageActivationTests() => ResetFeatureUsage();

    public void Dispose() => ResetFeatureUsage();

    [Fact]
    public void ConstructorsAndFactories_DoNotMarkFeatures()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();
        Uri agentEndpoint = new("https://test.services.ai.azure.com/api/projects/test/agents/test-agent/endpoint/protocols/openai");

        // Act
        _ = new FoundryChatClient(testClient.Client, "gpt-4o-mini");
        _ = new FoundryAgent(agentEndpoint, new FakeAuthenticationTokenProvider());
        _ = new FoundryMemoryProvider(
            testClient.Client,
            "memory-store",
            _ => new(new FoundryMemoryProviderScope("scope")));
#if NET8_0_OR_GREATER
        _ = new FoundryEvals(testClient.Client, "gpt-4o-mini");
#endif
        _ = FoundryAITool.CreateHostedMcpToolbox("toolbox");

        // Assert
        Assert.Null(GetFeatureToken());
    }

    [Fact]
    public async Task FoundryChatClient_StreamingMarksAtEnumerationAsync()
    {
        // Arrange
        using HttpHandlerAssert handler = new(_ => new HttpResponseMessage(HttpStatusCode.OK)
        {
            Content = new StringContent("data: [DONE]\n\n", Encoding.UTF8, "text/event-stream"),
        });
        using HttpClient httpClient = CreateHttpClient(handler);
        AIProjectClient projectClient = CreateProjectClient(httpClient);
        var chatClient = new FoundryChatClient(projectClient, "gpt-4o-mini");

        // Act
        IAsyncEnumerable<ChatResponseUpdate> updates =
            chatClient.GetStreamingResponseAsync([new ChatMessage(ChatRole.User, "Hello")]);

        // Assert
        Assert.Null(GetFeatureToken());

        await using IAsyncEnumerator<ChatResponseUpdate> enumerator = updates.GetAsyncEnumerator();
        try
        {
            _ = await enumerator.MoveNextAsync();
        }
        catch
        {
            // The minimal SSE body only needs to drive the request path.
        }

        AssertFeatureUsed(FeatureIndex.FoundryChatClient);
    }

    [Fact]
    public async Task FoundryAgent_ExecutionMarksAgentAndChatClientOnCurrentRequestAsync()
    {
        // Arrange
        string? userAgent = null;
        using HttpHandlerAssert handler = new(request =>
        {
            userAgent = GetHeader(request, "User-Agent");
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(TestDataUtil.GetOpenAIDefaultResponseJson(), Encoding.UTF8, "application/json"),
            };
        });
        using HttpClient httpClient = CreateHttpClient(handler);
        var options = new ProjectOpenAIClientOptions
        {
            Transport = new HttpClientPipelineTransport(httpClient),
        };
        var agent = new FoundryAgent(
            new Uri("https://test.services.ai.azure.com/api/projects/test/agents/test-agent/endpoint/protocols/openai"),
            new FakeAuthenticationTokenProvider(),
            options);

        // Act
        await agent.RunAsync("Hello");

        // Assert
        AssertFeatureUsed(FeatureIndex.FoundryChatClient);
        AssertFeatureUsed(FeatureIndex.FoundryAgent);
        Assert.Contains($"(feat={GetFeatureToken()})", userAgent, StringComparison.Ordinal);
    }

    [Fact]
    public async Task FoundryMemory_FirstProviderHookMarksFeatureAsync()
    {
        // Arrange
        using TestableAIProjectClient testClient = new();
        var provider = new FoundryMemoryProvider(
            testClient.Client,
            "memory-store",
            _ => new(new FoundryMemoryProviderScope("scope")));
        var context = new AIContextProvider.InvokingContext(
            new Mock<AIAgent>().Object,
            new Mock<AgentSession>().Object,
            new AIContext());

        // Act
        _ = await provider.InvokingAsync(context);

        // Assert
        AssertFeatureUsed(FeatureIndex.FoundryMemory);
    }

#if NET8_0_OR_GREATER
    [Fact]
    public async Task FoundryEvals_FirstEvaluationMarksFeatureAsync()
    {
        // Arrange
        using HttpHandlerAssert handler = new(_ => new HttpResponseMessage(HttpStatusCode.InternalServerError)
        {
            Content = new StringContent("{}", Encoding.UTF8, "application/json"),
        });
        using HttpClient httpClient = CreateHttpClient(handler);
        AIProjectClient projectClient = CreateProjectClient(httpClient);
        var evals = new FoundryEvals(projectClient, "gpt-4o-mini");

        // Act
        await Assert.ThrowsAnyAsync<Exception>(
            () => evals.EvaluateAsync([new EvalItem("question", "answer")]));

        // Assert
        AssertFeatureUsed(FeatureIndex.FoundryEvals);
    }
#endif

    [Fact]
    public async Task FoundryToolbox_MarksOnlyWhenMarkerParticipatesInOutgoingRequestAsync()
    {
        // Arrange
        string? requestBody = null;
        string? userAgent = null;
        using HttpHandlerAssert handler = new(async request =>
        {
            requestBody = request.Content is null
                ? null
                : await request.Content.ReadAsStringAsync().ConfigureAwait(false);
            userAgent = GetHeader(request, "User-Agent");
            return new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent(TestDataUtil.GetOpenAIDefaultResponseJson(), Encoding.UTF8, "application/json"),
            };
        });
        using HttpClient httpClient = CreateHttpClient(handler);
        AIProjectClient projectClient = CreateProjectClient(httpClient);
        var chatClient = new FoundryChatClient(projectClient, "gpt-4o-mini");
        var options = new ChatOptions
        {
            Tools = [FoundryAITool.CreateHostedMcpToolbox("calendar-tools", "v2")],
        };

        Assert.Null(GetFeatureToken());

        // Act
        _ = await chatClient.GetResponseAsync([new ChatMessage(ChatRole.User, "Hello")], options);

        // Assert
        Assert.Contains("\"type\":\"mcp\"", requestBody, StringComparison.Ordinal);
        Assert.Contains("calendar-tools", requestBody, StringComparison.Ordinal);
        Assert.Contains("v2", requestBody, StringComparison.Ordinal);
        AssertFeatureUsed(FeatureIndex.FoundryChatClient);
        AssertFeatureUsed(FeatureIndex.FoundryToolbox);
        Assert.Contains($"(feat={GetFeatureToken()})", userAgent, StringComparison.Ordinal);
    }

    private static AIProjectClient CreateProjectClient(HttpClient httpClient)
        => new(
            new Uri("https://test.services.ai.azure.com/api/projects/test"),
            new FakeAuthenticationTokenProvider(),
            new AIProjectClientOptions { Transport = new HttpClientPipelineTransport(httpClient) });

    private static HttpClient CreateHttpClient(HttpMessageHandler handler)
    {
#pragma warning disable CA5399
        return new HttpClient(handler, disposeHandler: false);
#pragma warning restore CA5399
    }

    private static string? GetHeader(HttpRequestMessage request, string name)
        => request.Headers.TryGetValues(name, out IEnumerable<string>? values)
            ? string.Join(" ", values)
            : null;

    private static string? GetFeatureToken()
        => (string?)GetFeatureUsageMethod("GetToken").Invoke(null, null);

    private static void AssertFeatureUsed(FeatureIndex feature)
    {
        string token = Assert.IsType<string>(GetFeatureToken());
        string hexMask = token.Substring(token.IndexOf('.') + 1);
        ulong mask = ulong.Parse(hexMask, NumberStyles.AllowHexSpecifier, CultureInfo.InvariantCulture);
        Assert.NotEqual(0UL, mask & (1UL << (int)feature));
    }

    private static void ResetFeatureUsage()
        => GetFeatureUsageMethod("ResetStateForTests").Invoke(null, null);

    private static MethodInfo GetFeatureUsageMethod(string name)
        => typeof(FeatureUsage).GetMethod(name, BindingFlags.Static | BindingFlags.NonPublic)
            ?? throw new InvalidOperationException($"FeatureUsage.{name} was not found.");
}
