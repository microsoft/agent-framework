// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.Mem0.UnitTests;

[Collection(nameof(FeatureUsageTestGroup))]
public sealed class FeatureUsageActivationTests : IDisposable
{
    [Fact]
    public async Task InvokingAsync_ActivatesMem0FeatureAsync()
    {
        // Arrange
        using HttpClient httpClient = new(new SuccessfulSearchHandler())
        {
            BaseAddress = new Uri("https://localhost/")
        };
        var provider = new Mem0Provider(
            httpClient,
            static _ => new Mem0Provider.State(new Mem0ProviderScope { UserId = "user" }));
        var context = new AIContextProvider.InvokingContext(
            new Mock<AIAgent>().Object,
            new TestAgentSession(),
            new AIContext { Messages = [new ChatMessage(ChatRole.User, "hello")] });
        FeatureUsageAssert.Reset();

        // Act
        _ = await provider.InvokingAsync(context);

        // Assert
        FeatureUsageAssert.Marked(60);
    }

    public void Dispose() => FeatureUsageAssert.Reset();

    private sealed class SuccessfulSearchHandler : HttpMessageHandler
    {
        protected override Task<HttpResponseMessage> SendAsync(
            HttpRequestMessage request,
            CancellationToken cancellationToken)
            => Task.FromResult(new HttpResponseMessage(HttpStatusCode.OK)
            {
                Content = new StringContent("[]")
            });
    }

    private sealed class TestAgentSession : AgentSession
    {
        public TestAgentSession()
        {
            this.StateBag = new AgentSessionStateBag();
        }
    }
}
