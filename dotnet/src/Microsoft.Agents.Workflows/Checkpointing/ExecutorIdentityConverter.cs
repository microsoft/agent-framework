// Copyright (c) Microsoft. All rights reserved.

using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Provides support for using <see cref="ExecutorIdentity"/> values as dictionary keys when serializing and deserializing JSON.
/// </summary>
internal sealed class ExecutorIdentityConverter() : JsonConverterDictionarySupportBase<ExecutorIdentity>
{
    protected override JsonTypeInfo<ExecutorIdentity> TypeInfo
        => WorkflowsJsonUtilities.JsonContext.Default.ExecutorIdentity;

    protected override ExecutorIdentity Parse(string propertyName)
    {
        if (propertyName.Length == 0)
        {
            return ExecutorIdentity.None;
        }

        if (propertyName[0] == '@')
        {
            return new() { Id = propertyName.Substring(1) };
        }

        throw new JsonException($"Invalid ExecutorIdentity key Expecting empty string or a value that is prefixed with '@'. Got '{propertyName}'");
    }

    protected override string Stringify(ExecutorIdentity value)
    {
        return value == ExecutorIdentity.None
             ? string.Empty
             : $"@{value.Id}";
    }
}
