// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using YamlDotNet.Core;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Microsoft.Extensions.AI.Agents.Yaml;

/// <summary>
/// Type converter custom deserialization for <see cref="Tool"/> from YAML.
/// </summary>
/// <remarks>
/// Required to correctly deserialize the <see cref="Tool"/> from YAML.
/// </remarks>
[RequiresDynamicCode("Calls YamlDotNet.Serialization.DeserializerBuilder.DeserializerBuilder()")]
internal sealed class ToolTypeConverter : IYamlTypeConverter
{
    /// <inheritdoc/>
    public bool Accepts(Type type)
    {
        return type == typeof(Tool);
    }

    /// <inheritdoc/>
    public object? ReadYaml(IParser parser, Type type, ObjectDeserializer rootDeserializer)
    {
        s_deserializer ??= new DeserializerBuilder()
            .WithNamingConvention(UnderscoredNamingConvention.Instance)
            .IgnoreUnmatchedProperties() // Required to ignore the 'type' property used as type discrimination. Otherwise, the "Property 'type' not found on type '{type.FullName}'" exception is thrown.
            .Build();

        var mapping = (Dictionary<string, object>)s_deserializer.Deserialize<Dictionary<string, object>>(parser);
        if (mapping.TryGetValue("type", out var toolTypeValue) && toolTypeValue is string toolType)
        {
            Tool tool = toolType switch
            {
                "function" => new FunctionTool(),
                "bing_search" => new BingSearchTool(),
                "file_search" => new FileSearchTool(),
                "mcp" => new McpTool(),
                "server" => new ServerTool(),
                _ => throw new InvalidOperationException($"Unknown tool type: {toolType}")
            };

            // Populate other properties if necessary
            return tool;
        }

        throw new InvalidOperationException("Invalid tool definition.");
    }

    /// <inheritdoc/>
    public void WriteYaml(IEmitter emitter, object? value, Type type, ObjectSerializer serializer)
    {
        throw new NotImplementedException();
    }

    /// <summary>
    /// The YamlDotNet deserializer instance.
    /// </summary>
    private static IDeserializer? s_deserializer;
}
