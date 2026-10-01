// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Numerics;
using System.Security.Cryptography;
using System.Text.Json;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Captures input content independently of mutable message objects without retaining the original history.
/// </summary>
internal static class CompactionInputFingerprint
{
    internal static string? Compute(IList<ChatMessage> messages, int count)
    {
        try
        {
            using SHA256 hash = SHA256.Create();
            using CryptoStream stream = new(Stream.Null, hash, CryptoStreamMode.Write);
            using Utf8JsonWriter writer = new(stream);
            writer.WriteStartArray();
            for (int i = 0; i < count; i++)
            {
                ChatMessage message = messages[i];
                writer.WriteStartArray();
                writer.WriteStringValue(message.Role.Value);
                writer.WriteStringValue(message.AuthorName);
                writer.WriteBooleanValue(CompactionMessageIndex.IsSummaryMessage(message));
                writer.WriteStartArray();
                foreach (AIContent content in message.Contents)
                {
                    if (content.GetType() == typeof(TextContent) && content is TextContent { Annotations: null, AdditionalProperties: null } text)
                    {
                        // Plain text needs no intermediate JSON document or property sorting.
                        writer.WriteStartArray();
                        writer.WriteStringValue("text");
                        writer.WriteStringValue(text.Text);
                        writer.WriteEndArray();
                        continue;
                    }

                    JsonElement serialized = JsonSerializer.SerializeToElement(content, AgentJsonUtilities.DefaultOptions.GetTypeInfo(typeof(AIContent)));
                    string? nullPropertyToOmit = content is FunctionResultContent ? "result" : null;
                    WriteCanonical(writer, serialized, nullPropertyToOmit);
                }

                writer.WriteEndArray();
                writer.WriteEndArray();
            }

            writer.WriteEndArray();
            writer.Flush();
            stream.FlushFinalBlock();
            return Convert.ToBase64String(hash.Hash!);
        }
        catch (NotSupportedException)
        {
            // Content without a serialization contract cannot validate a saved prefix; rebuild it instead.
            return null;
        }
        catch (JsonException)
        {
            return null;
        }
    }

    private static void WriteCanonical(Utf8JsonWriter writer, JsonElement value, string? nullPropertyToOmit = null)
    {
        switch (value.ValueKind)
        {
            case JsonValueKind.Object:
                writer.WriteStartObject();
                foreach (JsonProperty property in value.EnumerateObject().OrderBy(property => property.Name, StringComparer.Ordinal))
                {
                    // Optional payload fields are omitted for CLR null but written for a JSON null value.
                    if (nullPropertyToOmit is not null && property.NameEquals(nullPropertyToOmit) && property.Value.ValueKind == JsonValueKind.Null)
                    {
                        continue;
                    }

                    writer.WritePropertyName(property.Name);
                    WriteCanonical(writer, property.Value);
                }

                writer.WriteEndObject();
                break;
            case JsonValueKind.Array:
                writer.WriteStartArray();
                foreach (JsonElement item in value.EnumerateArray())
                {
                    WriteCanonical(writer, item);
                }

                writer.WriteEndArray();
                break;
            case JsonValueKind.String:
                writer.WriteStringValue(value.GetString());
                break;
            case JsonValueKind.Number:
                WriteNumber(writer, value.GetRawText());
                break;
            default:
                value.WriteTo(writer);
                break;
        }
    }

    private static void WriteNumber(Utf8JsonWriter writer, string number)
    {
        // Normalize the exact decimal coefficient and exponent without rounding through a CLR numeric type.
        int exponentIndex = number.IndexOfAny(['e', 'E']);
        BigInteger exponent = exponentIndex < 0 ? BigInteger.Zero : BigInteger.Parse(number.Substring(exponentIndex + 1), CultureInfo.InvariantCulture);
        string coefficient = exponentIndex < 0 ? number : number.Substring(0, exponentIndex);
        int decimalIndex = coefficient.IndexOf('.');
        if (decimalIndex >= 0)
        {
            exponent -= coefficient.Length - decimalIndex - 1;
            coefficient = coefficient.Remove(decimalIndex, 1);
        }

        bool negative = coefficient[0] == '-';
        if (negative)
        {
            coefficient = coefficient.Substring(1);
        }

        coefficient = coefficient.TrimStart('0');
        string trimmed = coefficient.TrimEnd('0');
        exponent += coefficient.Length - trimmed.Length;
        writer.WriteRawValue(trimmed.Length == 0 ? "0" : (negative ? "-" : "") + trimmed + "e" + exponent.ToString(CultureInfo.InvariantCulture), skipInputValidation: true);
    }
}
