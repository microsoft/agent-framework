// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Linq;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Bot.ObjectModel.Analysis;
using Microsoft.Bot.ObjectModel.PowerFx;
using Microsoft.Bot.ObjectModel.Yaml;
using Microsoft.Extensions.Configuration;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Helper methods for creating <see cref="BotElement"/> from YAML.
/// </summary>
internal static class AgentBotElementYaml
{
    /// <summary>
    /// Convert the given YAML text to a <see cref="PromptAgent"/> model.
    /// </summary>
    /// <param name="text">YAML representation of the <see cref="BotElement"/> to use to create the prompt function.</param>
    /// <param name="configuration">Optional <see cref="IConfiguration"/> instance which provides environment variables to the template.</param>
    [RequiresDynamicCode("Calls YamlDotNet.Serialization.DeserializerBuilder.DeserializerBuilder()")]
    public static PromptAgent FromYaml(string text, IConfiguration? configuration = null)
    {
        Throw.IfNullOrEmpty(text);

        var yamlReader = new StringReader(text);
        BotElement rootElement = YamlSerializer.Deserialize<BotElement>(yamlReader) ?? throw new InvalidDataException("Text does not contain a valid agent definition.");

        if (rootElement is not PromptAgent promptAgent)
        {
            throw new InvalidDataException($"Unsupported root element: {rootElement.GetType().Name}. Expected an {nameof(PromptAgent)}.");
        }

        var botDefinition = WrapPromptAgentWithBot(promptAgent, configuration);

        // Use PowerFx to check the expressions in the bot definition.
        SemanticModel semanticModel = botDefinition.GetSemanticModel(new PowerFxExpressionChecker(s_semanticFeatureConfig), s_semanticFeatureConfig);

        var values = new Dictionary<string, string?>();
        foreach (string variableName in semanticModel.GetAllEnvironmentVariablesReferencedInTheBot())
        {
            values[variableName] = configuration?[variableName];
        }

        // TODO: What do I have to do to apply the values are applied to the PromptAgent?

        return botDefinition.Descendants().OfType<PromptAgent>().First();
    }

    #region private
    private static readonly AgentFeatureConfiguration s_semanticFeatureConfig = new();

    private sealed class AgentFeatureConfiguration : IFeatureConfiguration
    {
        public long GetInt64Value(string settingName, long defaultValue) => defaultValue;

        public string GetStringValue(string settingName, string defaultValue) => defaultValue;

        public bool IsEnvironmentFeatureEnabled(string featureName, bool defaultValue) => true;

        public bool IsTenantFeatureEnabled(string featureName, bool defaultValue) => defaultValue;
    }

    public static BotDefinition WrapPromptAgentWithBot(this PromptAgent element, IConfiguration? configuration = null)
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

        if (configuration is not null)
        {
            foreach (var kvp in configuration.AsEnumerable().Where(kvp => kvp.Value is not null))
            {
                botBuilder.EnvironmentVariables.Add(new EnvironmentVariableDefinition.Builder()
                {
                    SchemaName = kvp.Key,
                    Id = Guid.NewGuid(),
                    DisplayName = kvp.Key,
                    ValueComponent = new EnvironmentVariableValue.Builder()
                    {
                        Id = Guid.NewGuid(),
                        Value = kvp.Value!,
                    },
                });
            }
        }

        return botBuilder.Build();
    }
    #endregion
}
