// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Verifies function-calling support end to end through the Responses channel: a ChatClientAgent built with
/// a tool over a deterministic two-turn fake chat client executes the tool (via the framework's
/// FunctionInvokingChatClient) and renders the final answer over POST /responses. No live model.
/// </summary>
public class FunctionCallingTests
{
    [Fact]
    public async Task ParameterlessTool_IsInvoked_AndFinalAnswerRenderedAsync()
    {
        // Arrange - a parameterless server-side tool the framework executes during the function-call loop
        var toolCalled = false;
        var weatherTool = AIFunctionFactory.Create(
            () => { toolCalled = true; return "sunny"; },
            name: "get_weather",
            description: "Gets the weather.");

        AIAgent agent = new ChatClientAgent(
            new FakeFunctionCallingChatClient(),
            instructions: "You are a weather assistant.",
            name: "weather",
            tools: [weatherTool]);

        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(agent).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(
            new System.Uri("http://localhost/responses"),
            Json("{ \"input\": \"What is the weather in Seattle?\" }"));
        var body = await response.Content.ReadAsStringAsync();

        // Assert - tool executed and the post-tool final answer was rendered
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.True(toolCalled, "the server-side tool should have been invoked by the function-calling loop");

        using var doc = JsonDocument.Parse(body);
        Assert.Equal("completed", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal(FakeFunctionCallingChatClient.FinalAnswer, MessageText(doc));
    }

    [Fact]
    public async Task ParameterizedTool_ReceivesArgument_AndFinalAnswerRenderedAsync()
    {
        // Arrange - a tool with a required parameter; the fake supplies the argument on the function call
        string? capturedCity = null;
        var weatherTool = AIFunctionFactory.Create(
            (string city) => { capturedCity = city; return $"sunny in {city}"; },
            name: "get_weather",
            description: "Gets the weather for a city.");

        var chatClient = new FakeFunctionCallingChatClient(new Dictionary<string, object?> { ["city"] = "Seattle" });
        AIAgent agent = new ChatClientAgent(chatClient, instructions: null, name: "weather", tools: [weatherTool]);

        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(agent).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(
            new System.Uri("http://localhost/responses"),
            Json("{ \"input\": \"What is the weather in Seattle?\" }"));
        var body = await response.Content.ReadAsStringAsync();

        // Assert - the argument bound and reached the tool, and the final answer was rendered
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        Assert.Equal("Seattle", capturedCity);

        using var doc = JsonDocument.Parse(body);
        Assert.Equal("completed", doc.RootElement.GetProperty("status").GetString());
        Assert.Equal(FakeFunctionCallingChatClient.FinalAnswer, MessageText(doc));
        // The function call is rendered as its own output item (rich rendering parity).
        Assert.Contains(doc.RootElement.GetProperty("output").EnumerateArray(), o => o.GetProperty("type").GetString() == "function_call");
    }

    [Fact]
    public async Task ToolCalling_StreamsFinalAnswerAsync()
    {
        // Arrange
        var weatherTool = AIFunctionFactory.Create(() => "sunny", name: "get_weather", description: "Gets the weather.");
        AIAgent agent = new ChatClientAgent(new FakeFunctionCallingChatClient(), instructions: null, name: "weather", tools: [weatherTool]);
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(agent).AddResponsesChannel());

        // Act
        var response = await app.Client.PostAsync(
            new System.Uri("http://localhost/responses"),
            Json("{ \"input\": \"weather in Seattle?\", \"stream\": true }"));
        var body = await response.Content.ReadAsStringAsync();
        var frames = Sse.Parse(body);

        // Assert - the final answer (after the tool loop) is delivered over SSE
        Assert.Equal("response.created", System.Linq.Enumerable.First(frames.Events()));
        Assert.Equal("response.completed", System.Linq.Enumerable.Last(frames.Events()));
        Assert.Contains(FakeFunctionCallingChatClient.FinalAnswer, body);
    }

    private static string? MessageText(JsonDocument doc)
    {
        foreach (var item in doc.RootElement.GetProperty("output").EnumerateArray())
        {
            if (item.GetProperty("type").GetString() == "message")
            {
                return item.GetProperty("content")[0].GetProperty("text").GetString();
            }
        }

        return null;
    }

    private static StringContent Json(string json) => new(json, System.Text.Encoding.UTF8, "application/json");
}
