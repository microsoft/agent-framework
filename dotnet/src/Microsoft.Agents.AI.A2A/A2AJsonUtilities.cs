// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.A2A;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides utility methods and configurations for JSON serialization operations for A2A agent types.
/// </summary>
public static partial class A2AJsonUtilities
{
    /// <summary>
    /// Gets the default <see cref="JsonSerializerOptions"/> instance used for JSON serialization operations of A2A agent types.
    /// </summary>
    /// <remarks>
    /// <para>
    /// For Native AOT or applications disabling <see cref="JsonSerializer.IsReflectionEnabledByDefault"/>, this instance
    /// includes source generated contracts for A2A agent types.
    /// </para>
    /// <para>
    /// It additionally turns on the following settings:
    /// <list type="number">
    /// <item><description>Enables <see cref="JsonSerializerDefaults.Web"/> defaults.</description></item>
    /// <item><description>Enables <see cref="JsonIgnoreCondition.WhenWritingNull"/> as the default ignore condition for properties.</description></item>
    /// <item><description>Enables <see cref="JsonNumberHandling.AllowReadingFromString"/> as the default number handling for number types.</description></item>
    /// <item><description>
    /// Enables <see cref="JavaScriptEncoder.UnsafeRelaxedJsonEscaping"/> when escaping JSON strings.
    /// Consuming applications must ensure that JSON outputs are adequately escaped before embedding in other document formats, such as HTML and XML.
    /// </description></item>
    /// </list>
    /// </para>
    /// </remarks>
    public static JsonSerializerOptions DefaultOptions { get; } = CreateDefaultOptions();

    /// <summary>
    /// Creates and configures the default JSON serialization options for agent abstraction types.
    /// </summary>
    /// <returns>The configured options.</returns>
    [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050:RequiresDynamicCode", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    private static JsonSerializerOptions CreateDefaultOptions()
    {
        // Copy the configuration from the source generated context.
        JsonSerializerOptions options = new(JsonContext.Default.Options)
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping, // same as AIJsonUtilities
        };

        // Chain in the resolvers from both AIJsonUtilities and our source generated context.
        // We want AIJsonUtilities first to ensure any M.E.AI types are handled via its resolver.
        options.TypeInfoResolverChain.Clear();
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);

        // If reflection-based serialization is enabled by default, this includes
        // the default type info resolver that utilizes reflection, but we need to manually
        // apply the same converter AIJsonUtilities adds for string-based enum serialization,
        // as that's not propagated as part of the resolver.
        if (JsonSerializer.IsReflectionEnabledByDefault)
        {
            options.Converters.Add(new JsonStringEnumConverter());
        }

        options.MakeReadOnly();
        return options;
    }

    [JsonSourceGenerationOptions(JsonSerializerDefaults.Web,
        UseStringEnumConverter = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        NumberHandling = JsonNumberHandling.AllowReadingFromString)]

    // A2A agent types
    [JsonSerializable(typeof(A2AAgentThread.A2AAgentThreadState))]
    [ExcludeFromCodeCoverage]
    private sealed partial class JsonContext : JsonSerializerContext;
}
