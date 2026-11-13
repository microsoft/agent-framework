// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using ModelContextProtocol.Protocol;

namespace Microsoft.Agents.AI;

/// <summary>
/// Converts skill cache scopes and rejects unrecognized values.
/// </summary>
internal sealed class McpSkillCacheScopeConverter : JsonConverter<CacheScope?>
{
    /// <inheritdoc/>
    public override CacheScope? Read(ref Utf8JsonReader reader, Type typeToConvert, JsonSerializerOptions options)
    {
        if (reader.TokenType == JsonTokenType.String)
        {
            string? value = reader.GetString();
            if (string.Equals(value, "public", StringComparison.OrdinalIgnoreCase))
            {
                return CacheScope.Public;
            }

            if (string.Equals(value, "private", StringComparison.OrdinalIgnoreCase))
            {
                return CacheScope.Private;
            }
        }

        throw new JsonException("The cacheScope must be 'public' or 'private'.");
    }

    /// <inheritdoc/>
    public override void Write(Utf8JsonWriter writer, CacheScope? value, JsonSerializerOptions options)
    {
        if (value is null)
        {
            writer.WriteNullValue();
            return;
        }

        writer.WriteStringValue(value switch
        {
            CacheScope.Public => "public",
            CacheScope.Private => "private",
            _ => throw new JsonException($"Unsupported {nameof(CacheScope)} value: {value}."),
        });
    }
}
