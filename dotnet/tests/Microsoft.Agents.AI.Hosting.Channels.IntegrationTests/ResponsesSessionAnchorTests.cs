// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Session-anchor precedence parity (Python <c>test_channel.py</c>): <c>previous_response_id</c> wins, else a
/// Foundry-lifted chat isolation key, else the freshly minted <c>response_id</c>; the chat header is ignored
/// outside the Foundry environment. Runs in the non-parallel isolation collection (process-wide env var).
/// </summary>
[Collection("IsolationEnvironment")]
public class ResponsesSessionAnchorTests
{
    private const string FoundryFlag = "FOUNDRY_HOSTING_ENVIRONMENT";

    [Fact]
    public async Task ChatHeader_IgnoredWithoutFlag_MintedIdAnchorsAsync()
    {
        // Arrange - no Foundry flag, so the chat header is not lifted
        using var env = new EnvVarScope(FoundryFlag, null);
        var hook = new CapturingRunHook();
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel(o => o.RunHook = hook));

        // Act
        await PostAsync(app, "{ \"input\": \"hi\" }", chatKey: "chat-abc");

        // Assert - the minted response id anchors the session, not the (ignored) header
        Assert.StartsWith("resp_", hook.Last!.Session!.IsolationKey);
    }

    [Fact]
    public async Task ChatHeader_AnchorsSessionUnderFlagAsync()
    {
        // Arrange
        using var env = new EnvVarScope(FoundryFlag, "1");
        var hook = new CapturingRunHook();
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel(o => o.RunHook = hook));

        // Act - no previous_response_id, so the lifted chat key anchors the session
        await PostAsync(app, "{ \"input\": \"hi\" }", chatKey: "chat-abc");

        // Assert
        Assert.Equal("chat-abc", hook.Last!.Session!.IsolationKey);
    }

    [Fact]
    public async Task PreviousResponseId_WinsOverChatHeaderAsync()
    {
        // Arrange
        using var env = new EnvVarScope(FoundryFlag, "1");
        var hook = new CapturingRunHook();
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel(o => o.RunHook = hook));

        // Act - both present; the explicit protocol anchor wins
        await PostAsync(app, "{ \"input\": \"hi\", \"previous_response_id\": \"resp_prev\" }", chatKey: "chat-abc");

        // Assert
        Assert.Equal("resp_prev", hook.Last!.Session!.IsolationKey);
    }

    private static async Task PostAsync(TestHostApp app, string body, string chatKey)
    {
        using var request = new HttpRequestMessage(HttpMethod.Post, new Uri("http://localhost/responses"))
        {
            Content = new StringContent(body, Encoding.UTF8, "application/json"),
        };
        request.Headers.TryAddWithoutValidation("x-agent-chat-isolation-key", chatKey);
        var response = await app.Client.SendAsync(request);
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }
}
