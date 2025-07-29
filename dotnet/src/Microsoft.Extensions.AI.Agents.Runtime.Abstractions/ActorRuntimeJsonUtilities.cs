// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Extensions.AI.Agents.Runtime;

/// <summary>Provides a collection of utility methods for working with JSON data in the context of actor runtime abstractions.</summary>
public static partial class AgentRuntimeAbstractionsJsonUtilities
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
    /// <item>Enables <see cref="JsonStringEnumConverter"/> for enum serialization.</item>
    /// </list>
    /// </para>
    /// </remarks>
    public static JsonSerializerOptions DefaultOptions { get; } = CreateDefaultOptions();

    /// <summary>
    /// Creates default options to use for actor runtime-related serialization.
    /// </summary>
    /// <returns>The configured options.</returns>
    [UnconditionalSuppressMessage("ReflectionAnalysis", "IL3050:RequiresDynamicCode", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    [UnconditionalSuppressMessage("Trimming", "IL2026:Members annotated with 'RequiresUnreferencedCodeAttribute' require dynamic access", Justification = "Converter is guarded by IsReflectionEnabledByDefault check.")]
    private static JsonSerializerOptions CreateDefaultOptions()
    {
        // Copy the configuration from the source generated context.
        JsonSerializerOptions options = new(JsonContext.Default.Options);

        options.MakeReadOnly();
        return options;
    }

    /// <summary>
    /// Source-generated JSON type information for use by all agent runtime abstractions.
    /// </summary>
    [JsonSourceGenerationOptions(
        JsonSerializerDefaults.Web,
        UseStringEnumConverter = true,
        DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
        WriteIndented = false)]
    [JsonSerializable(typeof(ActorId))]
    [JsonSerializable(typeof(ActorMessage))]
    [JsonSerializable(typeof(ActorReadOperation))]
    [JsonSerializable(typeof(ActorReadOperationBatch))]
    [JsonSerializable(typeof(ActorReadResult))]
    [JsonSerializable(typeof(ActorRequest))]
    [JsonSerializable(typeof(ActorRequestMessage))]
    [JsonSerializable(typeof(ActorRequestUpdate))]
    [JsonSerializable(typeof(ActorResponse))]
    [JsonSerializable(typeof(ActorResponseMessage))]
    [JsonSerializable(typeof(ActorType))]
    [JsonSerializable(typeof(ActorWriteOperation))]
    [JsonSerializable(typeof(ActorWriteOperationBatch))]
    [JsonSerializable(typeof(GetValueOperation))]
    [JsonSerializable(typeof(GetValueResult))]
    [JsonSerializable(typeof(JsonElement))]
    [JsonSerializable(typeof(ListKeysOperation))]
    [JsonSerializable(typeof(ListKeysResult))]
    [JsonSerializable(typeof(ReadResponse))]
    [JsonSerializable(typeof(RemoveKeyOperation))]
    [JsonSerializable(typeof(RequestStatus))]
    [JsonSerializable(typeof(SendRequestOperation))]
    [JsonSerializable(typeof(SetValueOperation))]
    [JsonSerializable(typeof(UpdateRequestOperation))]
    [JsonSerializable(typeof(WriteResponse))]
    internal sealed partial class JsonContext : JsonSerializerContext;
}
