// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Text.Json.Serialization.Metadata;
using M365Agent.Agents;
using Microsoft.Extensions.AI;

namespace M365Agent;

/// <summary>Provides a collection of utility methods for working with JSON data in the context of the application.</summary>
internal static partial class JsonUtilities
{
    /// <summary>
    /// Gets the <see cref="JsonSerializerOptions"/> singleton used as the default in JSON serialization operations.
    /// </summary>
    /// <remarks>
    /// <para>
    /// For Native AOT or applications disabling <see cref="JsonSerializer.IsReflectionEnabledByDefault"/>, this instance
    /// includes source generated contracts for all common exchange types contained in this library.
    /// </para>
    /// <para>
    /// It additionally turns on the following settings:
    /// <list type="number">
    /// <item>Enables <see cref="JsonSerializerDefaults.Web"/> defaults.</item>
    /// <item>Enables <see cref="JsonIgnoreCondition.WhenWritingNull"/> as the default ignore condition for properties.</item>
    /// <item>Enables <see cref="JsonNumberHandling.AllowReadingFromString"/> as the default number handling for number types.</item>
    /// </list>
    /// </para>
    /// </remarks>
    public static JsonSerializerOptions DefaultOptions { get; } = CreateDefaultOptions();

    /// <summary>
    /// Creates default options to use for agents-related serialization.
    /// </summary>
    /// <returns>The configured options.</returns>
    [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050:RequiresDynamicCode", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    private static JsonSerializerOptions CreateDefaultOptions()
    {
        // Copy the configuration from the source generated context.
        JsonSerializerOptions options = new(JsonContext.Default.Options)
        {
            // Chain in the resolvers from both AgentAbstractionsJsonUtilities and our source generated context.
            // We want AgentAbstractionsJsonUtilities first to ensure any M.E.AI types are handled via its resolver.
            TypeInfoResolver = JsonTypeInfoResolver.Combine(AIJsonUtilities.DefaultOptions.TypeInfoResolver, JsonContext.Default),
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping, // same as in AgentAbstractionsJsonUtilities and AIJsonUtilities
        };
        options.AddAIContentType<AdaptiveCardAIContent>(typeDiscriminatorId: "adaptiveCard");

        if (JsonSerializer.IsReflectionEnabledByDefault)
        {
            options.Converters.Add(new JsonStringEnumConverter());
        }

        options.MakeReadOnly();
        return options;
    }

    // Keep in sync with CreateDefaultOptions above.
    [JsonSourceGenerationOptions(JsonSerializerDefaults.Web,
        UseStringEnumConverter = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        NumberHandling = JsonNumberHandling.AllowReadingFromString)]

    // M365Agent specific types
    [JsonSerializable(typeof(AdaptiveCardAIContent))]

    [ExcludeFromCodeCoverage]
    internal sealed partial class JsonContext : JsonSerializerContext;
}
