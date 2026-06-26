// Copyright (c) Microsoft. All rights reserved.

using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>Validates the Responses channel's own wire mapping: JSON envelope, SSE frames, input parsing, errors.</summary>
public class ResponsesProtocolTests
{
    [Fact]
    public async Task Sync_StringInput_RendersResponsesJsonAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(new System.Uri("http://localhost/responses"), Json("{ \"input\": \"hi\" }"));
        var body = await response.Content.ReadAsStringAsync();

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        using var doc = JsonDocument.Parse(body);
        Assert.Equal("completed", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal(FakeChatAgent.Reply, doc.RootElement.GetProperty("output")[0].GetProperty("content")[0].GetProperty("text").GetString());
    }

    [Fact]
    public async Task Sync_InputItemArray_IsParsedAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new EchoAgent()).AddResponsesChannel());

        // Act - Responses input-item array shape (message envelope)
        var response = await app.Client.PostAsync(new System.Uri("http://localhost/responses"),
            Json("{ \"input\": [ { \"type\": \"message\", \"role\": \"user\", \"content\": \"piece\" } ] }"));
        var body = await response.Content.ReadAsStringAsync();

        // Assert - echo agent reflected the parsed user text
        Assert.Contains("piece", body);
    }

    [Fact]
    public async Task Streaming_EmitsCreatedDeltaCompletedAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(new System.Uri("http://localhost/responses"), Json("{ \"input\": \"hi\", \"stream\": true }"));
        var body = await response.Content.ReadAsStringAsync();
        var frames = Sse.Parse(body);
        var events = System.Linq.Enumerable.ToList(frames.Events());

        // Assert - frame sequence and reassembled text
        Assert.Equal("text/event-stream", response.Content.Headers.ContentType!.MediaType);
        Assert.Equal("response.created", events[0]);
        Assert.Contains("response.output_text.delta", events);
        Assert.Equal("response.completed", events[^1]);
        Assert.Contains(FakeChatAgent.Reply, body);
    }

    [Fact]
    public async Task MissingInput_Returns422Async()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(new System.Uri("http://localhost/responses"), Json("{ }"));

        // Assert - missing input is an unprocessable entity (Python parity), not a transport error
        Assert.Equal(HttpStatusCode.UnprocessableEntity, response.StatusCode);
    }

    [Fact]
    public async Task MalformedJson_Returns400Async()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(new System.Uri("http://localhost/responses"), Json("{ not json"));

        // Assert
        Assert.Equal(HttpStatusCode.BadRequest, response.StatusCode);
    }

    [Fact]
    public async Task WorkflowTarget_RendersCompletedResponseAsync()
    {
        // Arrange - workflow target with a run hook adapting the parsed input to the workflow's string input
        await using var app = await TestHostApp.StartAsync(b => b
            .AddAgentFrameworkHost(WorkflowFactory.Echo())
            .AddResponsesChannel(o => o.RunHook = new RewriteInputRunHook("ping")));

        // Act
        var response = await app.Client.PostAsync(new System.Uri("http://localhost/responses"), Json("{ \"input\": \"hi\" }"));

        // Assert
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
    }

    private static StringContent Json(string json) => new(json, System.Text.Encoding.UTF8, "application/json");
}
