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
/// Python-parity coverage for streaming finalization: the response hook is applied to the final streamed
/// result, and a mid-stream error is surfaced as a Responses <c>response.failed</c> SSE event rather than an
/// (invalid) post-headers JSON error.
/// </summary>
public class ResponsesStreamingFinalizeTests
{
    [Fact]
    public async Task MidStreamError_EmitsResponseFailedAsync()
    {
        // Arrange - an agent that yields one chunk then throws
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new ThrowingStreamAgent()).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json("{ \"input\": \"hi\", \"stream\": true }"));
        var body = await response.Content.ReadAsStringAsync();
        var events = System.Linq.Enumerable.ToList(Sse.Parse(body).Events());

        // Assert - the stream started (200 + created) and terminated with response.failed, not a JSON 500
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("text/event-stream", response.Content.Headers.ContentType!.MediaType);
        Assert.Equal("response.created", events[0]);
        Assert.Contains("response.failed", events);
        Assert.Equal("response.failed", events[^1]);
        Assert.Contains(ThrowingStreamAgent.ErrorMessage, body);
    }

    [Fact]
    public async Task StreamingAppliesResponseHookOnFinalAsync()
    {
        // Arrange
        var hook = new RecordingResponseHook();
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddResponsesChannel(o => o.ResponseHook = hook));

        // Act
        var response = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json("{ \"input\": \"hi\", \"stream\": true }"));
        var body = await response.Content.ReadAsStringAsync();

        // Assert - the response hook ran for the streamed request and the final completed event carries the text
        Assert.True(hook.Invoked);
        Assert.Contains(FakeChatAgent.Reply, body);
        Assert.EndsWith("\n\n", body);
    }

    private static StringContent Json(string json) => new(json, Encoding.UTF8, "application/json");
}
