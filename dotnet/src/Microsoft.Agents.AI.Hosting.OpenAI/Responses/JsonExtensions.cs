// Copyright (c) Microsoft. All rights reserved.

using System;
using System.ClientModel.Primitives;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Hosting.OpenAI.Responses.Generated;

namespace Microsoft.Agents.AI.Hosting.OpenAI.Responses;

/// <summary>
/// Extension methods for JSON serialization.
/// </summary>
internal static partial class JsonExtensions
{
    /// <summary>
    /// Gets the default JSON serializer options.
    /// </summary>
    /// <remarks>
    /// <para>
    /// This instance chains type resolvers from Microsoft.Agents.AI.Abstractions
    /// to support serialization of agent-related types.
    /// </para>
    /// <para>
    /// It additionally adds the <see cref="JsonModelConverter"/> for binary data serialization using
    /// the AOT-compatible constructor with <see cref="ModelReaderWriterOptions"/> and <see cref="AzureAIAgentsContext"/>.
    /// </para>
    /// </remarks>
    public static JsonSerializerOptions DefaultJsonSerializerOptions { get; } = CreateDefaultJsonSerializerOptions();

    /// <summary>
    /// Creates the default JSON serializer options with model converters and type resolver chaining.
    /// </summary>
    /// <returns>The default JSON serializer options.</returns>
    private static JsonSerializerOptions CreateDefaultJsonSerializerOptions()
    {
        JsonSerializerOptions options = new(JsonExtensionsContext.Default.Options);
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);
        options.Converters.Add(new JsonModelConverter(ModelReaderWriterOptions.Json, AzureAIAgentsContext.Default));
        options.MakeReadOnly();
        return options;
    }

    [JsonSourceGenerationOptions(JsonSerializerDefaults.Web,
        UseStringEnumConverter = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        NumberHandling = JsonNumberHandling.AllowReadingFromString)]
    [JsonSerializable(typeof(object))]
    [ExcludeFromCodeCoverage]
    private sealed partial class JsonExtensionsContext : JsonSerializerContext;

    /// <summary>
    /// Converts binary data to an object using JSON deserialization.
    /// </summary>
    /// <typeparam name="T">The type to deserialize to.</typeparam>
    /// <param name="data">The binary data to deserialize.</param>
    /// <param name="options">JSON serializer options.</param>
    /// <returns>The deserialized object or null if deserialization fails.</returns>
#pragma warning disable IL2026, IL3050 // JSON serialization requires dynamic access
    public static T? ToObject<T>(this BinaryData data, JsonSerializerOptions options) where T : class
    {
        try
        {
            return data.ToObjectFromJson<T>(options);
        }
        catch (JsonException)
        {
            return null;
        }
    }
#pragma warning restore IL2026, IL3050
}
