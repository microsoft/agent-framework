// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Text;
using System.Text.Json;
using System.Threading.Tasks;
using Microsoft.Agents.AI.Hosting.Channels.IntegrationTests.Support;
using Microsoft.Agents.AI.Hosting.Channels.Responses;
using Microsoft.Extensions.Hosting;

namespace Microsoft.Agents.AI.Hosting.Channels.IntegrationTests;

/// <summary>
/// Python-parity coverage for rich streaming (mirrors
/// test_sse_completed_preserves_streamed_multimodal_updates_when_finalize_fails): streamed reasoning and
/// function-call content emit their delta/done SSE events and dedicated output items, and the terminal
/// completed envelope carries the full multimodal output.
/// </summary>
public class ResponsesStreamingParityTests
{
    [Fact]
    public async Task MultimodalStream_EmitsRichEventsAndCompletedOutputAsync()
    {
        await using var app = await TestHostApp.StartAsync(b => b.AddAgentFrameworkHost(new MultimodalStreamAgent()).AddResponsesChannel());

        var response = await app.Client.PostAsync(new Uri("http://localhost/responses"), Json("{ \"input\": \"hi\", \"stream\": true }"));
        var body = await response.Content.ReadAsStringAsync();
        var events = Sse.Parse(body).Events().ToList();

        // The rich per-content event types are present.
        Assert.Contains("response.output_item.added", events);
        Assert.Contains("response.output_item.done", events);
        Assert.Contains("response.content_part.added", events);
        Assert.Contains("response.output_text.done", events);
        Assert.Contains("response.reasoning_text.delta", events);
        Assert.Contains("response.reasoning_text.done", events);
        Assert.Contains("response.function_call_arguments.delta", events);
        Assert.Contains("response.function_call_arguments.done", events);

        // The added output items, in order, cover message / reasoning / function_call / function_call_output.
        var addedTypes = new List<string>();
        JsonElement? functionCallAdded = null, functionOutputAdded = null;
        foreach (var (type, data) in Sse.Parse(body))
        {
            if (type != "response.output_item.added")
            {
                continue;
            }

            using var doc = JsonDocument.Parse(data);
            var item = doc.RootElement.GetProperty("item");
            var itemType = item.GetProperty("type").GetString()!;
            addedTypes.Add(itemType);
            if (itemType == "function_call")
            {
                functionCallAdded = item.Clone();
            }
            else if (itemType == "function_call_output")
            {
                functionOutputAdded = item.Clone();
            }
        }

        Assert.Equal(["message", "reasoning", "function_call", "function_call_output"], addedTypes);
        Assert.Equal(MultimodalStreamAgent.ToolName, functionCallAdded!.Value.GetProperty("name").GetString());
        Assert.Equal(string.Empty, functionCallAdded.Value.GetProperty("arguments").GetString());
        var addedParts = functionOutputAdded!.Value.GetProperty("output");
        Assert.Equal("input_image", addedParts[0].GetProperty("type").GetString());
        Assert.Equal(MultimodalStreamAgent.ImageUrl, addedParts[0].GetProperty("image_url").GetString());

        // The terminal completed envelope carries the full multimodal output.
        var completed = LastResponsePayload(body, "response.completed");
        var output = completed.GetProperty("output");
        Assert.Equal(MultimodalStreamAgent.Caption, output[0].GetProperty("content")[0].GetProperty("text").GetString());
        Assert.Equal(MultimodalStreamAgent.Reasoning, output[1].GetProperty("content")[0].GetProperty("text").GetString());
        Assert.Equal(MultimodalStreamAgent.ToolName, output[2].GetProperty("name").GetString());
        Assert.Equal("input_image", output[3].GetProperty("output")[0].GetProperty("type").GetString());
    }

    private static JsonElement LastResponsePayload(string body, string eventType)
    {
        JsonElement result = default;
        foreach (var (type, data) in Sse.Parse(body))
        {
            if (type == eventType)
            {
                using var doc = JsonDocument.Parse(data);
                result = doc.RootElement.GetProperty("response").Clone();
            }
        }

        return result;
    }

    private static StringContent Json(string json) => new(json, Encoding.UTF8, "application/json");
}
