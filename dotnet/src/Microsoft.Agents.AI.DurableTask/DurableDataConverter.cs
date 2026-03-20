// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Agents.AI.DurableTask.State;
using Microsoft.DurableTask;

namespace Microsoft.Agents.AI.DurableTask;

/// <summary>
/// Custom data converter for durable agents and workflows that ensures proper JSON serialization.
/// </summary>
/// <remarks>
/// This converter handles special cases like <see cref="DurableAgentState"/> using source-generated
/// JSON contexts for AOT compatibility, and falls back to reflection-based serialization for other types.
/// </remarks>
internal sealed class DurableDataConverter : DataConverter
{
    private static readonly JsonSerializerOptions s_options = new(DurableAgentJsonUtilities.DefaultOptions)
    {
        PropertyNamingPolicy = JsonNamingPolicy.CamelCase,
        PropertyNameCaseInsensitive = true,
    };

    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Fallback uses reflection when metadata unavailable.")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Fallback uses reflection when metadata unavailable.")]
    public override object? Deserialize(string? data, Type targetType)
    {
        if (data is null)
        {
            return null;
        }

        if (targetType == typeof(DurableAgentState))
        {
            return JsonSerializer.Deserialize(data, DurableAgentStateJsonContext.Default.DurableAgentState);
        }

        JsonTypeInfo? typeInfo = s_options.GetTypeInfo(targetType);
        return typeInfo is not null
            ? JsonSerializer.Deserialize(data, typeInfo)
            : JsonSerializer.Deserialize(data, targetType, s_options);
    }

    [return: NotNullIfNotNull(nameof(value))]
    [UnconditionalSuppressMessage("Trimming", "IL2026", Justification = "Fallback uses reflection when metadata unavailable.")]
    [UnconditionalSuppressMessage("AOT", "IL3050", Justification = "Fallback uses reflection when metadata unavailable.")]
    public override string? Serialize(object? value)
    {
        if (value is null)
        {
            return null;
        }

        if (value is DurableAgentState durableAgentState)
        {
            return JsonSerializer.Serialize(durableAgentState, DurableAgentStateJsonContext.Default.DurableAgentState);
        }

        JsonTypeInfo? typeInfo = s_options.GetTypeInfo(value.GetType());
        return typeInfo is not null
            ? JsonSerializer.Serialize(value, typeInfo)
            : JsonSerializer.Serialize(value, s_options);
    }
}
