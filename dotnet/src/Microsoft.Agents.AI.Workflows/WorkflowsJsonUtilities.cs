// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;
using Microsoft.Agents.AI.Workflows.Checkpointing;
using Microsoft.Agents.AI.Workflows.Execution;
using Microsoft.Extensions.AI;
using static Microsoft.Agents.AI.Workflows.WorkflowMessageStore;

namespace Microsoft.Agents.AI.Workflows;

/// <summary>Provides a collection of utility methods for working with JSON data in the context of workflows.</summary>
internal static partial class WorkflowsJsonUtilities
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

    public static JsonElement Serialize(this IEnumerable<ChatMessage> messages) =>
        JsonSerializer.SerializeToElement(messages, DefaultOptions.GetTypeInfo(typeof(IEnumerable<ChatMessage>)));

    public static List<ChatMessage> DeserializeMessages(this JsonElement element) =>
        (List<ChatMessage>?)element.Deserialize(DefaultOptions.GetTypeInfo(typeof(List<ChatMessage>))) ?? [];

    /// <summary>
    /// Creates default options to use for agents-related serialization.
    /// </summary>
    /// <returns>The configured options.</returns>
    [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050:RequiresDynamicCode", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    private static JsonSerializerOptions CreateDefaultOptions()
    {
        // Copy the configuration from the source generated context.
        JsonSerializerOptions options = new(JsonContext.Default.Options);

        // Chain with all supported types from Microsoft.Extensions.AI.Abstractions and Microsoft.Agents.AI.Abstractions.
        options.TypeInfoResolverChain.Add(AgentAbstractionsJsonUtilities.DefaultOptions.TypeInfoResolver!);

        options.MakeReadOnly();
        return options;
    }

    // Keep in sync with CreateDefaultOptions above.
    [JsonSourceGenerationOptions(JsonSerializerDefaults.Web,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        NumberHandling = JsonNumberHandling.AllowReadingFromString)]

    // Checkpointing Types
    [JsonSerializable(typeof(Checkpoint))]
    [JsonSerializable(typeof(CheckpointInfo))]
    [JsonSerializable(typeof(PortableValue))]
    [JsonSerializable(typeof(PortableMessageEnvelope))]
    [JsonSerializable(typeof(InMemoryCheckpointManager))]

    // Runtime State Types
    [JsonSerializable(typeof(ScopeKey))]
    [JsonSerializable(typeof(ScopeId))]
    [JsonSerializable(typeof(ExecutorIdentity))]
    [JsonSerializable(typeof(RunnerStateData))]

    // Workflow Representation Types
    [JsonSerializable(typeof(WorkflowInfo))]
    [JsonSerializable(typeof(EdgeConnection))]

    // Workflow-as-Agent
    [JsonSerializable(typeof(StoreState))]

    // Message Types
    [JsonSerializable(typeof(ChatMessage))]
    [JsonSerializable(typeof(ExternalRequest))]
    [JsonSerializable(typeof(ExternalResponse))]
    [JsonSerializable(typeof(TurnToken))]

    // Event Types
    //[JsonSerializable(typeof(WorkflowEvent))]
    //   Currently cannot be serialized because it includes Exceptions.
    //   We'll need a way to marshal this correct in the AgentRuntime case.
    //   For now this is okay, because we never serialize WorkflowEvents into
    //   checkpoints.
    [JsonSerializable(typeof(JsonElement))]

    [ExcludeFromCodeCoverage]
    internal sealed partial class JsonContext : JsonSerializerContext;
}
