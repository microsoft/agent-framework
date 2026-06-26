// Copyright (c) Microsoft. All rights reserved.

using System.Net.Http;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Verifies the host-owned hook pipeline on the Responses channel: run hook runs before the target,
/// response hook runs before serialization, and the stream-transform hook is applied while streaming.
/// </summary>
public class HookTests
{
    [Fact]
    public async Task RunHook_RewritesInputBeforeTargetAsync()
    {
        // Arrange - echo agent reflects whatever input the target receives; run hook rewrites it
        await using var app = await TestHostApp.StartAsync(b => b
            .AddAgentFrameworkHost(new EchoAgent())
            .AddResponsesChannel(o => o.RunHook = new RewriteInputRunHook("REWRITTEN")));

        // Act
        var response = await app.Client.PostAsync(new System.Uri("http://localhost/responses"), Json("{ \"input\": \"original\" }"));
        var body = await response.Content.ReadAsStringAsync();

        // Assert - target saw the rewritten input
        Assert.Contains("REWRITTEN", body);
        Assert.DoesNotContain("original", body);
    }

    [Fact]
    public async Task ResponseHook_RewritesResultBeforeSerializeAsync()
    {
        // Arrange - fake agent replies "Hello from fake agent!"; response hook uppercases it
        await using var app = await TestHostApp.StartAsync(b => b
            .AddAgentFrameworkHost(new FakeChatAgent())
            .AddResponsesChannel(o => o.ResponseHook = new UppercaseResponseHook()));

        // Act
        var response = await app.Client.PostAsync(new System.Uri("http://localhost/responses"), Json("{ \"input\": \"hi\" }"));
        var body = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.Contains(FakeChatAgent.Reply.ToUpperInvariant(), body);
    }

    [Fact]
    public async Task StreamTransformHook_AppliedWhileStreamingAsync()
    {
        // Arrange - prefix hook injects a "[X]" chunk ahead of the agent stream
        await using var app = await TestHostApp.StartAsync(b => b
            .AddAgentFrameworkHost(new FakeChatAgent())
            .AddResponsesChannel(o => o.StreamTransformHook = new PrefixStreamHook()));

        // Act
        var response = await app.Client.PostAsync(new System.Uri("http://localhost/responses"), Json("{ \"input\": \"hi\", \"stream\": true }"));
        var body = await response.Content.ReadAsStringAsync();
        var frames = Sse.Parse(body);

        // Assert - first delta is the injected marker
        Assert.Contains("[X]", body);
        var firstDelta = System.Array.Find(System.Linq.Enumerable.ToArray(frames), f => f.Event == "response.output_text.delta");
        Assert.Contains("[X]", firstDelta.Data);
    }

    private static StringContent Json(string json) => new(json, System.Text.Encoding.UTF8, "application/json");
}
