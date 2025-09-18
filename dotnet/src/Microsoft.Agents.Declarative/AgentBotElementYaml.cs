// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.IO;
using System.Linq;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;
using Microsoft.Bot.ObjectModel.Analysis;
using Microsoft.Bot.ObjectModel.PowerFx;
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

        // Use PowerFx to evaluate the expressions in the agent definition.
        SemanticModel semanticModel = agentDefinition.GetSemanticModel(new PowerFxExpressionChecker(s_semanticFeatureConfig), s_semanticFeatureConfig);
        var environmentVariables = semanticModel.GetAllEnvironmentVariablesReferencedInTheBot();

        return agentDefinition;
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

    public static TDialog WrapWithBot<TDialog>(this TDialog dialog) where TDialog : DialogBase
    {
        BotDefinition bot
            = new BotDefinition.Builder
            {
                Components =
                    {
                        new DialogComponent.Builder
                        {
                            SchemaName = dialog.HasSchemaName ? dialog.SchemaName : "default-schema",
                            Dialog = dialog.ToBuilder(),
                        }
                    }
            }.Build();

        return bot.Descendants().OfType<TDialog>().First();
    }
    #endregion
}
