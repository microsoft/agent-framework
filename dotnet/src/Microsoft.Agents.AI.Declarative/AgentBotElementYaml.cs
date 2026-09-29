// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Linq;
using Microsoft.Agents.ObjectModel;
using Microsoft.Agents.ObjectModel.Abstractions;
using Microsoft.Agents.ObjectModel.Analysis;
using Microsoft.Agents.ObjectModel.PowerFx;
using Microsoft.Agents.ObjectModel.Yaml;
using Microsoft.Extensions.Configuration;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Helper methods for creating <see cref="BotElement"/> from YAML.
/// </summary>
internal static class AgentBotElementYaml
{
    /// <summary>
    /// Convert the given YAML text to a <see cref="GptComponentMetadata"/> model.
    /// </summary>
    /// <param name="text">YAML representation of the <see cref="BotElement"/> to use to create the prompt function.</param>
    /// <param name="configuration">Optional <see cref="IConfiguration"/> instance which provides environment variables to the template.</param>
    /// <param name="allowedConfigurationVariables">Configuration keys that may be exposed when the YAML references them through <c>Env</c>.</param>
    [RequiresDynamicCode("Calls YamlDotNet.Serialization.DeserializerBuilder.DeserializerBuilder()")]
    public static GptComponentMetadata FromYaml(string text, IConfiguration? configuration = null, IEnumerable<string>? allowedConfigurationVariables = null)
    {
        Throw.IfNullOrEmpty(text);

        using var yamlReader = new StringReader(text);
        BotElement rootElement = YamlSerializer.Deserialize<BotElement>(yamlReader) ?? throw new InvalidDataException("Text does not contain a valid agent definition.");

        if (rootElement is not GptComponentMetadata promptAgent)
        {
            throw new InvalidDataException($"Unsupported root element: {rootElement.GetType().Name}. Expected an {nameof(GptComponentMetadata)}.");
        }

        var botDefinition = WrapPromptAgentWithBot(promptAgent, configuration, allowedConfigurationVariables);

        return botDefinition.Descendants().OfType<GptComponentMetadata>().First();
    }

    #region private
    private sealed class AgentFeatureConfiguration : IFeatureConfiguration
    {
        public long GetInt64Value(string settingName, long defaultValue) => defaultValue;

        public string GetStringValue(string settingName, string defaultValue) => defaultValue;

        public bool IsEnvironmentFeatureEnabled(string featureName, bool defaultValue) => true;

        public bool IsTenantFeatureEnabled(string featureName, bool defaultValue) => defaultValue;
    }

    public static BotDefinition WrapPromptAgentWithBot(this GptComponentMetadata element, IConfiguration? configuration = null, IEnumerable<string>? allowedConfigurationVariables = null)
    {
        var botBuilder =
            new BotDefinition.Builder
            {
                Components =
                {
                    new GptComponent.Builder
                    {
                        SchemaName = "default-schema",
                        Metadata = element.ToBuilder(),
                    }
                }
            };

        if (configuration is not null && allowedConfigurationVariables is not null)
        {
            HashSet<string> allowedVariables = new(allowedConfigurationVariables, StringComparer.OrdinalIgnoreCase);
            foreach (string variableName in GetReferencedEnvironmentVariableNames(element).Where(allowedVariables.Contains))
            {
                string? configurationValue = configuration[variableName];
                if (configurationValue is null)
                {
                    continue;
                }

                botBuilder.EnvironmentVariables.Add(new EnvironmentVariableDefinition.Builder()
                {
                    SchemaName = variableName,
                    Id = Guid.NewGuid(),
                    DisplayName = variableName,
                    ValueComponent = new EnvironmentVariableValue.Builder()
                    {
                        Id = Guid.NewGuid(),
                        Value = configurationValue,
                    },
                });
            }
        }

        return botBuilder.Build();
    }

    internal static ISet<string> GetReferencedEnvironmentVariableNames(GptComponentMetadata element)
    {
        var botDefinition = WrapPromptAgentWithBot(element);
        SemanticModel semanticModel = botDefinition.GetSemanticModel(new PowerFxExpressionChecker(new AgentFeatureConfiguration()), new AgentFeatureConfiguration());

        return semanticModel.GetAllEnvironmentVariablesReferencedInTheBot();
    }
    #endregion
}
