// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Buffers;
using System.Collections.Generic;
using System.IO;
using System.Text;
using System.Text.Json;
using System.Text.RegularExpressions;
using Microsoft.Shared.Diagnostics;
using YamlDotNet.Core;
using YamlDotNet.Core.Events;

namespace Microsoft.Agents.AI;

/// <summary>
/// Reads the YAML metadata block, or frontmatter, at the start of <c>SKILL.md</c> and converts it to JSON.
/// </summary>
/// <remarks>
/// <para>
/// Preserves all fields and their key casing, including fields the framework does not recognize.
/// The Markdown instructions after the metadata block are not parsed.
/// </para>
/// <para>
/// Unquoted <c>true</c>, <c>false</c>, <c>null</c>, and JSON-format numbers become the corresponding JSON values.
/// Other text remains a string, including quoted values and multiline text. Empty unquoted values become null.
/// </para>
/// <para>
/// Requires an object with unique string keys. YAML tags, anchors, aliases, and merge keys are not supported.
/// Input that exceeds the resource size or nesting limit is rejected.
/// </para>
/// </remarks>
internal static partial class McpSkillFrontmatterParser
{
    private const int MaxDepth = 64;

    /// <summary>
    /// Parses the metadata block between the opening <c>---</c> lines in <c>SKILL.md</c>.
    /// </summary>
    /// <param name="content">The complete <c>SKILL.md</c> text, including metadata and instructions.</param>
    /// <param name="maxResourceSizeBytes">The maximum UTF-8 size, in bytes, of the complete file.</param>
    /// <returns>A JSON object containing every metadata field.</returns>
    /// <exception cref="InvalidOperationException">
    /// The file exceeds the size limit, or its metadata is missing, invalid, unsupported, or too deeply nested.
    /// </exception>
    internal static JsonElement Parse(string content, long maxResourceSizeBytes)
    {
        _ = Throw.IfNull(content);
        ArgumentOutOfRangeException.ThrowIfNegativeOrZero(maxResourceSizeBytes);

        // Character count is a cheap lower bound; count UTF-8 bytes only if the input could fit.
        if (content.Length > maxResourceSizeBytes || Encoding.UTF8.GetByteCount(content) > maxResourceSizeBytes)
        {
            throw new InvalidOperationException($"SKILL.md exceeds the maximum resource size of {maxResourceSizeBytes} bytes.");
        }

        using StringReader reader = new(ExtractFrontmatter(content));
        var parser = new Parser(reader);
        var buffer = new ArrayBufferWriter<byte>();
        using var writer = new Utf8JsonWriter(buffer, new JsonWriterOptions { MaxDepth = MaxDepth });

        try
        {
            parser.Consume<StreamStart>();
            parser.Consume<DocumentStart>();
            if (!parser.Accept<MappingStart>(out _))
            {
                throw new InvalidOperationException("SKILL.md frontmatter must be a YAML mapping.");
            }

            WriteValue(parser, writer, 0);
            // Require the stream to end after this document so a second YAML document cannot be ignored.
            parser.Consume<DocumentEnd>();
            parser.Consume<StreamEnd>();
            writer.Flush();
        }
        catch (YamlException exception)
        {
            throw new InvalidOperationException("SKILL.md contains invalid or unsupported YAML frontmatter.", exception);
        }
        catch (ArgumentOutOfRangeException exception) when (exception.ParamName is "highSurrogate" or "lowSurrogate" or "utf32")
        {
            // YamlDotNet can report malformed Unicode escapes through character-conversion exceptions.
            throw new InvalidOperationException("SKILL.md frontmatter contains an invalid Unicode escape.", exception);
        }

        using JsonDocument document = JsonDocument.Parse(buffer.WrittenMemory, new JsonDocumentOptions { MaxDepth = MaxDepth });

        // The returned value must remain usable after this temporary document is disposed.
        return document.RootElement.Clone();
    }

    /// <summary>
    /// Extracts the YAML between the first two delimiter lines, leaving out the Markdown instructions.
    /// Accepts an optional leading byte order mark and preserves line breaks needed by multiline values.
    /// </summary>
    private static string ExtractFrontmatter(string content)
    {
        using StringReader reader = new(content);
        ReadOnlySpan<char> firstLine = reader.ReadLine().AsSpan();
        if (!firstLine.IsEmpty && firstLine[0] == '\uFEFF')
        {
            firstLine = firstLine[1..];
        }

        if (!IsDelimiter(firstLine))
        {
            throw new InvalidOperationException("SKILL.md must start with a YAML frontmatter delimiter.");
        }

        StringBuilder yaml = new();
        while (reader.ReadLine() is { } line)
        {
            if (IsDelimiter(line.AsSpan()))
            {
                // Stop before the instructions, which may contain text that is not valid YAML.
                return yaml.ToString();
            }

            // Preserve blank lines and the final line break for YAML block-scalar chomping.
            yaml.Append(line).Append('\n');
        }

        throw new InvalidOperationException("SKILL.md has no closing YAML frontmatter delimiter.");
    }

    /// <summary>
    /// Recognizes a line containing only <c>---</c>, with optional trailing spaces or tabs but no indentation.
    /// </summary>
    private static bool IsDelimiter(ReadOnlySpan<char> line) => line.TrimEnd(" \t").SequenceEqual("---");

    /// <summary>
    /// Writes the current YAML value and its children as JSON, then advances the parser past that value.
    /// Rejects unsupported nodes, invalid or duplicate object keys, and excessive nesting before writing them.
    /// </summary>
    /// <param name="parser">The YAML parser positioned at the value to convert.</param>
    /// <param name="writer">The destination JSON writer.</param>
    /// <param name="depth">The number of enclosing objects and arrays; zero for the root object.</param>
    private static void WriteValue(Parser parser, Utf8JsonWriter writer, int depth)
    {
        if (parser.Accept<AnchorAlias>(out _))
        {
            throw new InvalidOperationException("YAML aliases are not supported in skill frontmatter.");
        }

        NodeEvent node = parser.Require<NodeEvent>();
        ValidateNode(node);

        switch (node)
        {
            case Scalar scalar:
                WriteScalar(writer, scalar);
                parser.MoveNext();
                break;

            case MappingStart:
                ValidateDepth(depth);
                writer.WriteStartObject();
                parser.MoveNext();
                // Track decoded keys per object: name and "name" are duplicates, but name and Name are distinct.
                HashSet<string> keys = new(StringComparer.Ordinal);
                while (!parser.TryConsume<MappingEnd>(out _))
                {
                    Scalar key = parser.Consume<Scalar>();
                    ValidateNode(key);
                    // JSON requires string keys; treating YAML's << merge operator as a field would change its meaning.
                    if (GetScalarKind(key) != JsonValueKind.String || (key.Style == ScalarStyle.Plain && key.Value == "<<"))
                    {
                        throw new InvalidOperationException("Skill frontmatter requires string keys and does not support YAML merge keys.");
                    }

                    if (!keys.Add(key.Value))
                    {
                        throw new InvalidOperationException($"Skill frontmatter contains duplicate key '{key.Value}'.");
                    }

                    writer.WritePropertyName(key.Value);
                    WriteValue(parser, writer, depth + 1);
                }

                writer.WriteEndObject();
                break;

            case SequenceStart:
                ValidateDepth(depth);
                writer.WriteStartArray();
                parser.MoveNext();
                while (!parser.TryConsume<SequenceEnd>(out _))
                {
                    WriteValue(parser, writer, depth + 1);
                }

                writer.WriteEndArray();
                break;

            default:
                throw new InvalidOperationException("Skill frontmatter contains an unsupported YAML node.");
        }
    }

    /// <summary>
    /// Rejects anchors, which name reusable values, and tags, which override how YAML values are interpreted.
    /// Neither is supported by this JSON conversion.
    /// </summary>
    private static void ValidateNode(NodeEvent node)
    {
        if (!node.Anchor.IsEmpty || !node.Tag.IsEmpty)
        {
            throw new InvalidOperationException("YAML anchors and tags are not supported in skill frontmatter.");
        }
    }

    /// <summary>
    /// Checks the nesting limit before entering another object or array, counting the root object toward the limit.
    /// </summary>
    private static void ValidateDepth(int depth)
    {
        // Check before descending so deeply nested input is rejected without exhausting the call stack.
        if (depth >= MaxDepth)
        {
            throw new InvalidOperationException($"Skill frontmatter exceeds the maximum nesting depth of {MaxDepth}.");
        }
    }

    /// <summary>
    /// Writes a single YAML value as a JSON string, number, boolean, or null using the parser's conversion rules.
    /// </summary>
    private static void WriteScalar(Utf8JsonWriter writer, Scalar scalar)
    {
        switch (GetScalarKind(scalar))
        {
            case JsonValueKind.Null:
                writer.WriteNullValue();
                break;
            case JsonValueKind.True:
                writer.WriteBooleanValue(true);
                break;
            case JsonValueKind.False:
                writer.WriteBooleanValue(false);
                break;
            case JsonValueKind.Number:
                // Preserve precision and exponent spelling instead of converting through a CLR numeric type.
                writer.WriteRawValue(scalar.Value);
                break;
            default:
                writer.WriteStringValue(scalar.Value);
                break;
        }
    }

    /// <summary>
    /// Determines the JSON type of a single YAML value without changing its text.
    /// Quoted and multiline values stay strings; only unquoted JSON literals and empty values receive other types.
    /// </summary>
    private static JsonValueKind GetScalarKind(Scalar scalar)
    {
        // Quoting or using a multiline block makes values such as "true" and "42" text, not JSON literals.
        if (scalar.Style != ScalarStyle.Plain)
        {
            return JsonValueKind.String;
        }

        return scalar.Value switch
        {
            "" or "null" => JsonValueKind.Null,
            "true" => JsonValueKind.True,
            "false" => JsonValueKind.False,
            _ => JsonNumberRegex().IsMatch(scalar.Value) ? JsonValueKind.Number : JsonValueKind.String,
        };
    }

    /// <summary>
    /// Matches JSON-format numbers, excluding YAML-specific forms such as <c>0x10</c> and <c>01</c>.
    /// </summary>
    [GeneratedRegex(@"\A-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?\z", RegexOptions.CultureInvariant | RegexOptions.NonBacktracking)]
    private static partial Regex JsonNumberRegex();
}
