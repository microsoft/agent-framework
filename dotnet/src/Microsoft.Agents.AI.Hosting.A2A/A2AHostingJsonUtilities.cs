// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;

namespace Microsoft.Agents.AI.Hosting.A2A;

/// <summary>
/// Provides JSON serialization options for A2A Hosting APIs to support AOT and trimming.
/// </summary>
public static class A2AHostingJsonUtilities
{
    /// <summary>
    /// Gets the default <see cref="JsonSerializerOptions"/> instance used for A2A Hosting serialization.
    /// </summary>
    public static JsonSerializerOptions DefaultOptions { get; } = CreateDefaultOptions();

    private static JsonSerializerOptions CreateDefaultOptions()
    {
        JsonSerializerOptions options = new(global::A2A.A2AJsonUtilities.DefaultOptions);

        // Chain in the resolvers from both AgentAbstractionsJsonUtilities and the A2A SDK context.
        // AgentAbstractionsJsonUtilities is first to ensure M.E.AI types (e.g. ResponseContinuationToken)
        // are handled via its resolver, followed by the A2A SDK resolver for protocol types.
        options.TypeInfoResolverChain.Clear();
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);
        options.TypeInfoResolverChain.Add(global::A2A.A2AJsonUtilities.DefaultOptions.TypeInfoResolver!);

        options.MakeReadOnly();
        return options;
    }
}
