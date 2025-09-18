// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Provides support for using <see cref="EdgeId"/> values as dictionary keys when serializing and deserializing JSON.
/// </summary>
internal sealed class EdgeIdConverter : JsonConverterDictionarySupportBase<EdgeId>
{
    protected override JsonTypeInfo<EdgeId> TypeInfo => WorkflowsJsonUtilities.JsonContext.Default.EdgeId;

    protected override EdgeId Parse(string propertyName)
    {
        if (int.TryParse(propertyName, out int edgeId))
        {
            return new(edgeId);
        }

        throw new JsonException($"Cannot deserialize EdgeId from JSON propery name '{propertyName}'");
    }

    protected override string Stringify([DisallowNull] EdgeId value)
    {
        return value.EdgeIndex.ToString();
    }
}
