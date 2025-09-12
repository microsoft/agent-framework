// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.IO;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Yaml;
using Microsoft.Extensions.Configuration;
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
    /// <remarks>
    /// The <see cref="BotElement"/> will be normalized by calling
    /// <see cref="Normalize(GptComponentMetadata, IConfiguration?)"/> before being returned.
    /// </remarks>
    /// <param name="text">YAML representation of the <see cref="BotElement"/> to use to create the prompt function.</param>
    /// <param name="configuration">Optional instance of <see cref="IConfiguration"/> which can provide configuration settings.</param>
    [RequiresDynamicCode("Calls YamlDotNet.Serialization.DeserializerBuilder.DeserializerBuilder()")]
    public static GptComponentMetadata FromYaml(string text, IConfiguration? configuration = null)
    {
        Throw.IfNullOrEmpty(text);

        var yamlReader = new StringReader(text);
        BotElement rootElement = YamlSerializer.Deserialize<BotElement>(yamlReader) ?? throw new InvalidDataException("Text does not contain a valid agent definition.");

        if (rootElement is not GptComponentMetadata agentDefinition)
        {
            throw new InvalidDataException($"Unsupported root element: {rootElement.GetType().Name}. Expected an {nameof(GptComponentMetadata)}.");
        }

        return Normalize(agentDefinition, configuration);
    }

    /// <summary>
    /// Normalizing the <see cref="AgentDefinition"/> makes the following changes:
    /// <ul>
    ///     <li>
    ///     All string properties that are delimited with "${" and "}" will be resolved as variables from the provided <see cref="IConfiguration"/>.
    ///     </li>
    /// </ul>
    /// </summary>
    /// <param name="agentDefinition">AgentDefinition instance to update.</param>
    /// <param name="configuration">Optional instance of <see cref="IConfiguration"/> which can provide configuration settings.</param>
    public static GptComponentMetadata Normalize(GptComponentMetadata agentDefinition, IConfiguration? configuration)
    {
        Throw.IfNull(agentDefinition);

        if (configuration is not null)
        {
            //agentDefinition!.Normalize(configuration);
        }

        return agentDefinition!;
    }
}
