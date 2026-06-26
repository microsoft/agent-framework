// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Python-parity coverage for the Responses channel's output rendering: mixed content renders as typed output
/// items (reasoning / function_call / function_call_output / message), and streaming emits the richer SSE
/// event sequence (output_item.added, content_part.added, output_text.delta/done, content_part.done,
/// output_item.done) rather than only created/delta/completed.
/// </summary>
public class ResponsesRenderingTests
{
    [Fact]
    public async Task MixedContent_RendersTypedOutputItemsAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new RichContentAgent()).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json("{ \"input\": \"hi\" }"));
        var body = await response.Content.ReadAsStringAsync();

        // Assert - typed items in order, each with the expected payload
        using var doc = JsonDocument.Parse(body);
        var output = doc.RootElement.GetProperty("output");
        var types = new List<string>();
        string? reasoningText = null, functionOutput = null, messageText = null, callName = null;
        foreach (var item in output.EnumerateArray())
        {
            var type = item.GetProperty("type").GetString()!;
            types.Add(type);
            switch (type)
            {
                case "reasoning": reasoningText = item.GetProperty("content")[0].GetProperty("text").GetString(); break;
                case "function_call": callName = item.GetProperty("name").GetString(); break;
                case "function_call_output": functionOutput = item.GetProperty("output").GetString(); break;
                case "message": messageText = item.GetProperty("content")[0].GetProperty("text").GetString(); break;
            }
        }

        Assert.Equal("reasoning,function_call,function_call_output,message", string.Join(",", types));
        Assert.Equal(RichContentAgent.ReasoningText, reasoningText);
        Assert.Equal(RichContentAgent.ToolName, callName);
        Assert.Equal("sunny in Seattle", functionOutput);
        Assert.Equal(RichContentAgent.FinalText, messageText);
    }

    [Fact]
    public async Task Envelope_HasExpectedShapeAsync()
    {
        // Arrange - no model in the request, so the envelope falls back to "agent"
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json("{ \"input\": \"hi\" }"));
        var body = await response.Content.ReadAsStringAsync();

        // Assert
        using var doc = JsonDocument.Parse(body);
        var root = doc.RootElement;
        Assert.Equal("response", root.GetProperty("object").GetString());
        Assert.StartsWith("resp_", root.GetProperty("id").GetString());
        Assert.True(root.GetProperty("created_at").GetInt64() > 0);
        Assert.Equal("completed", root.GetProperty("status").GetString());
        Assert.Equal("agent", root.GetProperty("model").GetString());
    }

    [Fact]
    public async Task FunctionCall_CarriesCallIdNameAndArgumentsAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new RichContentAgent()).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json("{ \"input\": \"hi\" }"));
        var body = await response.Content.ReadAsStringAsync();

        // Assert
        using var doc = JsonDocument.Parse(body);
        JsonElement? call = null;
        foreach (var item in doc.RootElement.GetProperty("output").EnumerateArray())
        {
            if (item.GetProperty("type").GetString() == "function_call")
            {
                call = item;
                break;
            }
        }

        Assert.NotNull(call);
        Assert.Equal(RichContentAgent.CallId, call!.Value.GetProperty("call_id").GetString());
        Assert.Equal(RichContentAgent.ToolName, call.Value.GetProperty("name").GetString());
        Assert.Contains("Seattle", call.Value.GetProperty("arguments").GetString());
    }

    [Fact]
    public async Task Streaming_EmitsRichEventSequenceAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json("{ \"input\": \"hi\", \"stream\": true }"));
        var body = await response.Content.ReadAsStringAsync();
        var events = System.Linq.Enumerable.ToList(Sse.Parse(body).Events());

        // Assert - the richer Responses event shape is present and well-ordered
        int Idx(string name) => events.IndexOf(name);
        Assert.Equal("response.created", events[0]);
        Assert.Equal("response.completed", events[^1]);
        Assert.True(Idx("response.output_item.added") < Idx("response.content_part.added"));
        Assert.True(Idx("response.content_part.added") < Idx("response.output_text.delta"));
        Assert.True(Idx("response.output_text.delta") < Idx("response.output_text.done"));
        Assert.True(Idx("response.output_text.done") < Idx("response.content_part.done"));
        Assert.True(Idx("response.content_part.done") < Idx("response.output_item.done"));
        Assert.True(Idx("response.output_item.done") < Idx("response.completed"));
    }

    [Fact]
    public async Task EmptyPath_MountsAtAppRootAsync()
    {
        // Arrange - Path "" mounts the Responses route at the app root
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddResponsesChannel(o => o.Path = ""));

        // Act
        var atRoot = await app.Client.PostAsync(new Uri("http://localhost/"), Json("{ \"input\": \"hi\" }"));
        var atResponses = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json("{ \"input\": \"hi\" }"));

        // Assert
        Assert.Equal(System.Net.HttpStatusCode.OK, atRoot.StatusCode);
        Assert.Equal(System.Net.HttpStatusCode.NotFound, atResponses.StatusCode);
    }

    [Fact]
    public async Task CustomPath_MountsRouteAndDefaultPath404sAsync()
    {
        // Arrange
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new FakeChatAgent()).AddResponsesChannel(o => o.Path = "/v1/responses"));

        // Act
        var atCustom = await app.Client.PostAsync(new Uri("http://localhost/v1/responses"), Json("{ \"input\": \"hi\" }"));
        var atDefault = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json("{ \"input\": \"hi\" }"));

        // Assert
        Assert.Equal(System.Net.HttpStatusCode.OK, atCustom.StatusCode);
        Assert.Equal(System.Net.HttpStatusCode.NotFound, atDefault.StatusCode);
    }

    private static StringContent Json(string json) => new(json, Encoding.UTF8, "application/json");
}
