// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;

namespace Microsoft.Agents.Workflows.UnitTests;

[JsonSourceGenerationOptions(JsonSerializerDefaults.Web,
    DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull,
    NumberHandling = JsonNumberHandling.AllowReadingFromString)]

internal sealed class TestJsonSerializable
{
    public int Id { get; set; }
    public string Name { get; set; } = string.Empty;

    public override bool Equals(object? obj)
    {
        if (obj is null)
        {
            return false;
        }

        if (obj is not TestJsonSerializable other)
        {
            return false;
        }

        return this.Id == other.Id && this.Name == other.Name;
    }

    public override int GetHashCode() => HashCode.Combine(this.Id, this.Name);
}
