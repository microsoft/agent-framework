// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.AI;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Python-parity coverage for the Responses channel's content rendering (mirrors test_channel.py): multimodal
/// output items, function-result media projection, call/result coalescing, and raw-item passthrough/replacement.
/// Each case posts to <c>/responses</c> and asserts the rendered <c>output</c> array.
/// </summary>
public class ResponsesContentRenderingParityTests
{
    [Fact]
    public async Task MultimodalResponse_RendersReasoningCallResultMessageAsync()
    {
        var contents = new List<AIContent>
        {
            new TextReasoningContent("checking"),
            new FunctionCallContent("call_1", "collect_media", new Dictionary<string, object?> { ["city"] = "Seattle" }),
            new FunctionResultContent("call_1", new List<AIContent>
            {
                new TextContent("caption"),
                new UriContent("https://example.com/cat.png", "image/png"),
                new HostedFileContent("file_pdf") { MediaType = "application/pdf" },
            }),
            new TextContent("done"),
        };

        var output = await PostAsync(new ScriptedAgent([.. contents]));

        Assert.Equal(["reasoning", "function_call", "function_call_output", "message"], TypesOf(output));
        Assert.Equal("checking", output[0].GetProperty("content")[0].GetProperty("text").GetString());
        Assert.Equal("collect_media", output[1].GetProperty("name").GetString());

        var args = JsonNode.Parse(output[1].GetProperty("arguments").GetString()!)!;
        Assert.Equal("Seattle", args["city"]!.GetValue<string>());

        var parts = output[2].GetProperty("output");
        Assert.Equal("input_text", parts[0].GetProperty("type").GetString());
        Assert.Equal("caption", parts[0].GetProperty("text").GetString());
        Assert.Equal("input_image", parts[1].GetProperty("type").GetString());
        Assert.Equal("https://example.com/cat.png", parts[1].GetProperty("image_url").GetString());
        Assert.Equal("auto", parts[1].GetProperty("detail").GetString());
        Assert.Equal("input_file", parts[2].GetProperty("type").GetString());
        Assert.Equal("file_pdf", parts[2].GetProperty("file_id").GetString());

        Assert.Equal("done", output[3].GetProperty("content")[0].GetProperty("text").GetString());
    }

    [Fact]
    public async Task FunctionResultException_IsPreservedAsStringAsync()
    {
        var result = new FunctionResultContent("call_1", null) { Exception = new InvalidOperationException("tool failed") };
        var output = await PostAsync(new ScriptedAgent(result));

        Assert.Equal("function_call_output", output[0].GetProperty("type").GetString());
        Assert.Equal("tool failed", output[0].GetProperty("output").GetString());
    }

    [Fact]
    public async Task ImageGenerationAndMcpCallResult_CoalesceWithinMessageAsync()
    {
        var contents = new List<AIContent>
        {
            new ImageGenerationToolCallContent("ig_1"),
            new ImageGenerationToolResultContent("ig_1")
            {
                Outputs = [new DataContent("data:image/png;base64,aGVsbG8=", "image/png")],
            },
            new McpServerToolCallContent("mcp_1", "lookup", "weather")
            {
                Arguments = new Dictionary<string, object?> { ["city"] = "Seattle" },
            },
            new McpServerToolResultContent("mcp_1") { Outputs = [new TextContent("sunny")] },
        };

        var output = await PostAsync(new ScriptedAgent([.. contents]));

        Assert.Equal(["image_generation_call", "mcp_call"], TypesOf(output));
        Assert.Equal("ig_1", output[0].GetProperty("id").GetString());
        Assert.Equal("aGVsbG8=", output[0].GetProperty("result").GetString());

        Assert.Equal("mcp_1", output[1].GetProperty("id").GetString());
        Assert.Equal("weather", output[1].GetProperty("server_label").GetString());
        Assert.Equal("lookup", output[1].GetProperty("name").GetString());
        Assert.Equal("sunny", output[1].GetProperty("output").GetString());
        var args = JsonNode.Parse(output[1].GetProperty("arguments").GetString()!)!;
        Assert.Equal("Seattle", args["city"]!.GetValue<string>());
    }

    [Fact]
    public async Task McpCallResult_CoalesceAcrossMessagesAsync()
    {
        var messages = new List<ChatMessage>
        {
            new(ChatRole.Assistant, [new McpServerToolCallContent("mcp_1", "lookup", "weather")
            {
                Arguments = new Dictionary<string, object?> { ["city"] = "Seattle" },
            }]),
            new(ChatRole.Tool, [new McpServerToolResultContent("mcp_1") { Outputs = [new TextContent("sunny")] }]),
        };

        var output = await PostAsync(new ScriptedAgent(messages));

        Assert.Equal(["mcp_call"], TypesOf(output));
        Assert.Equal("mcp_1", output[0].GetProperty("id").GetString());
        Assert.Equal("sunny", output[0].GetProperty("output").GetString());
    }

    [Fact]
    public async Task RawResponsesOutputItem_IsPreservedVerbatimAsync()
    {
        JsonObject Raw() => new()
        {
            ["id"] = "ig_1",
            ["type"] = "image_generation_call",
            ["result"] = "base64-image",
            ["status"] = "completed",
        };

        var contents = new List<AIContent>
        {
            new ImageGenerationToolCallContent("ig_1") { RawRepresentation = Raw() },
            new ImageGenerationToolResultContent("ig_1") { RawRepresentation = Raw() },
        };

        var output = await PostAsync(new ScriptedAgent([.. contents]));

        Assert.Equal(1, output.GetArrayLength());
        Assert.Equal("image_generation_call", output[0].GetProperty("type").GetString());
        Assert.Equal("ig_1", output[0].GetProperty("id").GetString());
        Assert.Equal("base64-image", output[0].GetProperty("result").GetString());
        Assert.Equal("completed", output[0].GetProperty("status").GetString());
    }

    [Fact]
    public async Task LaterRawOutputItem_ReplacesEarlierPartialAsync()
    {
        JsonObject Partial() => new()
        {
            ["id"] = "mcp_1",
            ["type"] = "mcp_call",
            ["server_label"] = "weather",
            ["name"] = "lookup",
            ["arguments"] = "{}",
            ["status"] = "in_progress",
        };

        JsonObject Completed()
        {
            var c = Partial();
            c["status"] = "completed";
            c["output"] = "sunny";
            return c;
        }

        var contents = new List<AIContent>
        {
            new McpServerToolCallContent("mcp_1", "lookup", "weather") { RawRepresentation = Partial() },
            new McpServerToolResultContent("mcp_1") { RawRepresentation = Completed() },
        };

        var output = await PostAsync(new ScriptedAgent([.. contents]));

        Assert.Equal(1, output.GetArrayLength());
        Assert.Equal("completed", output[0].GetProperty("status").GetString());
        Assert.Equal("sunny", output[0].GetProperty("output").GetString());
    }

    private static async Task<JsonElement> PostAsync(AIAgent agent)
    {
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(agent).AddResponsesChannel());
        var response = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json("{ \"input\": \"hi\" }"));
        Assert.Equal(HttpStatusCode.OK, response.StatusCode);
        var body = await response.Content.ReadAsStringAsync();
        using var doc = JsonDocument.Parse(body);
        return doc.RootElement.GetProperty("output").Clone();
    }

    private static List<string> TypesOf(JsonElement output)
    {
        var types = new List<string>();
        foreach (var item in output.EnumerateArray())
        {
            types.Add(item.GetProperty("type").GetString()!);
        }

        return types;
    }

    private static StringContent Json(string json) => new(json, Encoding.UTF8, "application/json");
}
