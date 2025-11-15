// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Encodings.Web;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.DurableTask.State;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>Provides JSON serialization utilities and source-generated contracts for Durable Agent types.</summary>
/// <remarks>
/// <para>
/// This mirrors the pattern used by other libraries (e.g. <c>WorkflowsJsonUtilities</c>) to enable Native AOT and trimming
/// friendly serialization without relying on runtime reflection. It establishes a singleton <see cref="JsonSerializerOptions"/>
/// instance that is preconfigured with:
/// </para>
/// <list type="number">
/// <item><description><see cref="JsonSerializerDefaults.Web"/> baseline defaults.</description></item>
/// <item><description><see cref="JsonIgnoreCondition.WhenWritingNull"/> for default null-value suppression.</description></item>
/// <item><description><see cref="JsonNumberHandling.AllowReadingFromString"/> to tolerate numbers encoded as strings.</description></item>
/// <item><description>Chained type info resolvers from shared agent abstractions to cover cross-package types (e.g. <see cref="ChatMessage"/>, <see cref="AgentRunResponse"/>).</description></item>
/// </list>
/// <para>
/// Keep the list of <c>[JsonSerializable]</c> types in sync with the Durable Agent data model anytime new state or request/response
/// containers are introduced that must round-trip via JSON.
/// </para>
/// </remarks>
internal static partial class DurableAgentJsonUtilities
{
    /// <summary>
    /// Gets the singleton <see cref="JsonSerializerOptions"/> used for Durable Agent serialization.
    /// </summary>
    public static JsonSerializerOptions DefaultOptions { get; } = CreateDefaultOptions();

    /// <summary>
    /// Serializes a sequence of chat messages using the durable agent default options.
    /// </summary>
    /// <param name="messages">The messages to serialize.</param>
    /// <returns>A <see cref="JsonElement"/> representing the serialized messages.</returns>
    public static JsonElement Serialize(this IEnumerable<ChatMessage> messages) =>
        JsonSerializer.SerializeToElement(messages, DefaultOptions.GetTypeInfo(typeof(IEnumerable<ChatMessage>)));

    /// <summary>
    /// Deserializes chat messages from a <see cref="JsonElement"/> using durable agent options.
    /// </summary>
    /// <param name="element">The JSON element containing the messages.</param>
    /// <returns>The deserialized list of chat messages.</returns>
    public static List<ChatMessage> DeserializeMessages(this JsonElement element) =>
        (List<ChatMessage>?)element.Deserialize(DefaultOptions.GetTypeInfo(typeof(List<ChatMessage>))) ?? [];

    /// <summary>
    /// Creates the configured <see cref="JsonSerializerOptions"/> instance for durable agents.
    /// </summary>
    /// <returns>The configured options.</returns>
    [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050:RequiresDynamicCode", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    private static JsonSerializerOptions CreateDefaultOptions()
    {
        // Base configuration from the source-generated context below.
        JsonSerializerOptions options = new(JsonContext.Default.Options)
        {
            Encoder = JavaScriptEncoder.UnsafeRelaxedJsonEscaping, // same as AgentAbstractionsJsonUtilities and AIJsonUtilities
        };

        // Chain in shared abstractions resolver (Microsoft.Extensions.AI + Agent abstractions) so dependent types are covered.
        options.TypeInfoResolverChain.Clear();
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);
        options.TypeInfoResolverChain.Add(JsonContext.Default.Options.TypeInfoResolver!);

        if (JsonSerializer.IsReflectionEnabledByDefault)
        {
            options.Converters.Add(new JsonStringEnumConverter());
        }

        options.MakeReadOnly();
        return options;
    }

    // Keep in sync with CreateDefaultOptions above.
    [JsonSourceGenerationOptions(JsonSerializerDefaults.Web,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        NumberHandling = JsonNumberHandling.AllowReadingFromString)]

    // Durable Agent State Types
    [JsonSerializable(typeof(DurableAgentState))]
    [JsonSerializable(typeof(DurableAgentThread))]

    // Request Types
    [JsonSerializable(typeof(RunRequest))]

    // Primitive / Supporting Types
    [JsonSerializable(typeof(ChatMessage))]
    [JsonSerializable(typeof(JsonElement))]

    [ExcludeFromCodeCoverage]
    internal sealed partial class JsonContext : JsonSerializerContext;
}
