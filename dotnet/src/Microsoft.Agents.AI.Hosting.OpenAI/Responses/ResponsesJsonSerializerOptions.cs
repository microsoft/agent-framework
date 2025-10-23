// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Extension methods for JSON serialization.
/// </summary>
internal static class ResponsesJsonSerializerOptions
{
    /// <summary>
    /// Gets the default JSON serializer options.
    /// </summary>
    public static JsonSerializerOptions Default { get; } = Create();

    private static JsonSerializerOptions Create()
    {
        JsonSerializerOptions options = new(ResponsesJsonContext.Default.Options);
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);
        options.MakeReadOnly();
        return options;
    }
}
