// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.GithubCopilot;

/// <summary>
/// Provides utility methods and configurations for JSON serialization operations within the GitHub Copilot agent implementation.
/// </summary>
internal static partial class GithubCopilotJsonUtilities
{
    /// <summary>
    /// Gets the default <see cref="JsonSerializerOptions"/> instance used for JSON serialization operations.
    /// </summary>
    public static JsonSerializerOptions DefaultOptions { get; } = CreateDefaultOptions();

    /// <summary>
    /// Creates and configures the default JSON serialization options.
    /// </summary>
    /// <returns>The configured options.</returns>
    [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050:RequiresDynamicCode", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    private static JsonSerializerOptions CreateDefaultOptions()
    {
        // Copy the configuration from the source generated context.
        JsonSerializerOptions options = new(JsonContext.Default.Options)
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping,
        };

        // Chain in the resolvers from both AgentAbstractionsJsonUtilities and our source generated context.
        options.TypeInfoResolverChain.Clear();
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);
        options.TypeInfoResolverChain.Add(JsonContext.Default.Options.TypeInfoResolver!);

        // If reflection-based serialization is enabled by default, include string-based enum serialization.
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
    [JsonSerializable(typeof(GithubCopilotAgentThread.State))]
    [ExcludeFromCodeCoverage]
    private sealed partial class JsonContext : JsonSerializerContext;
}
