// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.Hosting.OpenAI.ChatCompletions;

/// <summary>
/// Extension methods for JSON serialization.
/// </summary>
internal static class ChatCompletionsJsonSerializerOptions
{
    /// <summary>
    /// Gets the default JSON serializer options.
    /// </summary>
    public static JsonSerializerOptions Default { get; } = Create();

    private static JsonSerializerOptions Create()
    {
        JsonSerializerOptions options = new(ChatCompletionsJsonContext.Default.Options);

        // Chain in the resolvers from both AgentAbstractionsJsonUtilities and our source generated context.
        // We want AgentAbstractionsJsonUtilities first to ensure any M.E.AI types are handled via its resolver.
        options.TypeInfoResolverChain.Clear();
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);
        options.TypeInfoResolverChain.Add(ChatCompletionsJsonContext.Default.Options.TypeInfoResolver!);

        options.MakeReadOnly();
        return options;
    }
}
