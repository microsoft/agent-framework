// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel;
using System.ClientModel.Primitives;
using System.Net.Http;
using System.Reflection;
using Microsoft.Extensions.AI;
using OpenAI;

#pragma warning disable OPENAI001, MEAI001

namespace Microsoft.Agents.AI.Foundry.Hosting.UnitTests;

/// <summary>
/// Verifies the dedup behavior of <see cref="FoundryHostingExtensions.TryApplyUserAgent"/>.
/// In hosted mode, <see cref="AgentFrameworkResponseHandler"/> calls this method on every
/// inbound request resolution. For singleton agents this would grow MEAI's
/// <c>OpenAIRequestPolicies._entries</c> array unboundedly without per-instance dedup.
/// </summary>
public sealed class HostedTryApplyUserAgentDedupTests
{
    [Fact]
    public void TryApplyUserAgent_RepeatedCalls_OnSameAgent_RegistersPolicyOnce()
    {
        // Arrange
        using var http = new HttpClient(new NoopHandler());
        var openAIClient = new OpenAIClient(new ApiKeyCredential("fake"),
            new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http) });
        IChatClient chatClient = openAIClient.GetResponsesClient().AsIChatClient();
        AIAgent agent = new ChatClientAgent(chatClient);

        // Act: simulate per-request hosted resolution running this many times.
        for (int i = 0; i < 50; i++)
        {
            FoundryHostingExtensions.TryApplyUserAgent(agent);
        }

        // Assert: the underlying OpenAIRequestPolicies has exactly one entry, not 50.
        var policies = chatClient.GetService<OpenAIRequestPolicies>();
        Assert.NotNull(policies);
        Assert.Equal(1, EntriesCount(policies!));
    }

    [Fact]
    public void TryApplyUserAgent_AcrossDistinctAgents_RegistersPolicyOncePerChatClient()
    {
        // Arrange: two independent chat clients.
        using var http1 = new HttpClient(new NoopHandler());
        using var http2 = new HttpClient(new NoopHandler());
        var client1 = new OpenAIClient(new ApiKeyCredential("k1"),
            new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http1) });
        var client2 = new OpenAIClient(new ApiKeyCredential("k2"),
            new OpenAIClientOptions { Transport = new HttpClientPipelineTransport(http2) });

        IChatClient cc1 = client1.GetResponsesClient().AsIChatClient();
        IChatClient cc2 = client2.GetResponsesClient().AsIChatClient();

        AIAgent a1 = new ChatClientAgent(cc1);
        AIAgent a2 = new ChatClientAgent(cc2);

        // Act
        for (int i = 0; i < 10; i++)
        {
            FoundryHostingExtensions.TryApplyUserAgent(a1);
            FoundryHostingExtensions.TryApplyUserAgent(a2);
        }

        // Assert: each chat client's OpenAIRequestPolicies has exactly one entry.
        Assert.Equal(1, EntriesCount(cc1.GetService<OpenAIRequestPolicies>()!));
        Assert.Equal(1, EntriesCount(cc2.GetService<OpenAIRequestPolicies>()!));
    }

    private static int EntriesCount(OpenAIRequestPolicies policies)
    {
        var field = typeof(OpenAIRequestPolicies).GetField("_entries", BindingFlags.Instance | BindingFlags.NonPublic);
        var array = (Array?)field?.GetValue(policies);
        return array?.Length ?? -1;
    }

    private sealed class NoopHandler : HttpMessageHandler
    {
        protected override System.Threading.Tasks.Task<HttpResponseMessage> SendAsync(HttpRequestMessage request, System.Threading.CancellationToken cancellationToken)
            => System.Threading.Tasks.Task.FromResult(new HttpResponseMessage(System.Net.HttpStatusCode.OK));
    }
}
