// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Hosting.OpenAI.UnitTests;

/// <summary>
/// Provides permissive <see cref="OpenAIResponsesMapOptions"/> and <see cref="OpenAIChatCompletionsMapOptions"/>
/// that map the request-supplied generation and tool settings onto the agent run.
/// </summary>
/// <remarks>
/// The production default rejects request-supplied settings so that callers cannot override a
/// self-contained agent. These helpers opt in to the legacy behavior for conformance tests that
/// exercise the wire format end-to-end.
/// </remarks>
internal static class PermissiveMapOptions
{
    public static OpenAIResponsesMapOptions Responses() => new()
    {
        RunOptionsFactory = static request =>
        {
            var chatOptions = new ChatOptions
            {
                Temperature = (float?)request.Temperature,
                TopP = (float?)request.TopP,
                MaxOutputTokens = request.MaxOutputTokens,
                Instructions = request.Instructions,
                ModelId = request.Model,
                ToolMode = request.ToolChoice,
            };

            return new ChatClientAgentRunOptions(chatOptions);
        }
    };

    public static OpenAIChatCompletionsMapOptions ChatCompletions() => new()
    {
        RunOptionsFactory = static request =>
        {
            var chatOptions = new ChatOptions
            {
                Temperature = request.Temperature,
                TopP = request.TopP,
                MaxOutputTokens = request.MaxOutputTokens,
                FrequencyPenalty = request.FrequencyPenalty,
                PresencePenalty = request.PresencePenalty,
                Seed = request.Seed,
                StopSequences = request.StopSequences is { Count: > 0 } stop ? [.. stop] : null,
                ResponseFormat = request.ResponseFormat,
                ToolMode = request.ToolChoice,
                Tools = request.Tools is { Count: > 0 } tools ? tools.ToList() : null,
                ModelId = request.Model,
            };

            return new ChatClientAgentRunOptions(chatOptions);
        }
    };
}
