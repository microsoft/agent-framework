// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Text.Json.Nodes;
using System.Threading.Tasks;
using AgentHooks;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.AgentHooks.UnitTests;

internal static class TestHelpers
{
    public static List<ChatMessage> UserMessage(string text) => [new ChatMessage(ChatRole.User, text)];

    public static AIFunction WeatherTool(Action<string>? onInvoke = null) =>
        AIFunctionFactory.Create(
            (string location) =>
            {
                onInvoke?.Invoke(location);
                return $"weather:{location}";
            },
            "get_weather");

    public static ChatClientAgentOptions AgentOptionsWithTools(params AITool[] tools) => new()
    {
        Name = "assistant",
        ChatOptions = new ChatOptions { Tools = [.. tools] },
    };

    public static Verdict TransformTarget(JsonNode? value) =>
        new(Decision.Transform, Transform: new Transform("$target", value));

    public static async Task<List<AgentResponseUpdate>> CollectAsync(IAsyncEnumerable<AgentResponseUpdate> stream)
    {
        List<AgentResponseUpdate> updates = [];
        await foreach (var update in stream)
        {
            updates.Add(update);
        }

        return updates;
    }
}
