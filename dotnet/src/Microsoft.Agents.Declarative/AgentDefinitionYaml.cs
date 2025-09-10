// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Extensions.Configuration;
using Microsoft.Shared.Diagnostics;
using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace Microsoft.Agents.Declarative;

/// <summary>
/// Helper methods for creating <see cref="AgentDefinition"/> from YAML.
/// </summary>
internal static class AgentDefinitionYaml
{
    /// <summary>
    /// Convert the given YAML text to a <see cref="AgentDefinition"/> model.
    /// </summary>
    /// <remarks>
    /// The <see cref="AgentDefinition"/> will be normalized by calling
    /// <see cref="Normalize(AgentDefinition, IConfiguration?)"/> before being returned.
    /// </remarks>
    /// <param name="text">YAML representation of the <see cref="AgentDefinition"/> to use to create the prompt function.</param>
    /// <param name="configuration">Optional instance of <see cref="IConfiguration"/> which can provide configuration settings.</param>
    [RequiresDynamicCode("Calls YamlDotNet.Serialization.DeserializerBuilder.DeserializerBuilder()")]
    public static AgentDefinition FromYaml(string text, IConfiguration? configuration = null)
    {
        Throw.IfNullOrEmpty(text);

        var deserializer = new DeserializerBuilder()
            .WithNamingConvention(UnderscoredNamingConvention.Instance)
            .WithTypeConverter(new ToolTypeConverter())
            .Build();

        var agentDefinition = deserializer.Deserialize<AgentDefinition>(text);
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
    public static AgentDefinition Normalize(AgentDefinition agentDefinition, IConfiguration? configuration)
    {
        Throw.IfNull(agentDefinition);

        if (configuration is not null)
        {
            //agentDefinition!.Normalize(configuration);
        }

        return agentDefinition!;
    }
}
