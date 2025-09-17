// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.IO;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Yaml;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.Declarative;

/// <summary>
/// Helper methods for creating <see cref="BotElement"/> from YAML.
/// </summary>
internal static class AgentBotElementYaml
{
    /// <summary>
    /// Convert the given YAML text to a <see cref="GptComponentMetadata"/> model.
    /// </summary>
    /// <param name="text">YAML representation of the <see cref="BotElement"/> to use to create the prompt function.</param>
    [RequiresDynamicCode("Calls YamlDotNet.Serialization.DeserializerBuilder.DeserializerBuilder()")]
    public static GptComponentMetadata FromYaml(string text)
    {
        Throw.IfNullOrEmpty(text);

        var yamlReader = new StringReader(text);
        BotElement rootElement = YamlSerializer.Deserialize<BotElement>(yamlReader) ?? throw new InvalidDataException("Text does not contain a valid agent definition.");

        if (rootElement is not GptComponentMetadata agentDefinition)
        {
            throw new InvalidDataException($"Unsupported root element: {rootElement.GetType().Name}. Expected an {nameof(GptComponentMetadata)}.");
        }

        return agentDefinition;
    }
}
