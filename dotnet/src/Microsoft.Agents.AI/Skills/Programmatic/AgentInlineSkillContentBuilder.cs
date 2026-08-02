// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// Internal helper that builds XML-structured content strings for code-defined and class-based skills.
/// </summary>
internal static class AgentInlineSkillContentBuilder
{
    /// <summary>
    /// Builds the complete skill content containing name, description, instructions, resources, and script parameter schemas.
    /// </summary>
    /// <param name="name">The skill name.</param>
    /// <param name="description">The skill description.</param>
    /// <param name="instructions">The raw instructions text.</param>
    /// <param name="resources">Optional resources associated with the skill.</param>
    /// <param name="scripts">Optional scripts associated with the skill.</param>
    /// <returns>An XML-structured content string.</returns>
    public static string Build(
        string name,
        string description,
        string instructions,
        IReadOnlyList<AgentSkillResource>? resources,
        IReadOnlyList<AgentSkillScript>? scripts)
    {
        _ = Throw.IfNullOrWhitespace(name);
        _ = Throw.IfNullOrWhitespace(description);
        _ = Throw.IfNullOrWhitespace(instructions);

        var sb = new StringBuilder();

        sb.Append($"<name>{EscapeXmlString(name)}</name>\n")
        .Append($"<description>{EscapeXmlString(description)}</description>\n\n")
        .Append("<instructions>\n")
        .Append(EscapeXmlString(instructions))
        .Append("\n</instructions>");

        sb.Append('\n');
        sb.Append(BuildAvailableResourcesBlock(resources ?? []));
        sb.Append('\n');
        sb.Append(BuildAvailableScriptsBlock(scripts ?? []));

        return sb.ToString();
    }

    /// <summary>
    /// Builds an <c>&lt;available_resources&gt;...&lt;/available_resources&gt;</c> XML block for the given resources.
    /// Each resource is emitted as a self-closing <c>&lt;resource name="..."/&gt;</c> element. When the list is empty,
    /// a self-closing <c>&lt;available_resources /&gt;</c> element is returned. This block lets the model know which
    /// resources can be read (or that there are none) so it does not hallucinate resource names.
    /// </summary>
    /// <param name="resources">The resources to include in the block.</param>
    /// <returns>
    /// An XML string starting with <c>\n&lt;available_resources&gt;</c>, or <c>\n&lt;available_resources /&gt;</c> if the list is empty.
    /// </returns>
    public static string BuildAvailableResourcesBlock(IReadOnlyList<AgentSkillResource> resources)
    {
        _ = Throw.IfNull(resources);

        if (resources.Count == 0)
        {
            // Emit an empty element so the model knows no resources are available and does not hallucinate resource names.
            return "\n<available_resources />";
        }

        var sb = new StringBuilder();
        sb.Append("\n<available_resources>\n");

        foreach (var resource in resources)
        {
            if (!string.IsNullOrWhiteSpace(resource.Description))
            {
                sb.Append($"  <resource name=\"{EscapeXmlString(resource.Name)}\" description=\"{EscapeXmlString(resource.Description)}\"/>\n");
            }
            else
            {
                sb.Append($"  <resource name=\"{EscapeXmlString(resource.Name)}\"/>\n");
            }
        }

        sb.Append("</available_resources>");

        return sb.ToString();
    }

    /// <summary>
    /// Builds an <c>&lt;available_scripts&gt;...&lt;/available_scripts&gt;</c> XML block for the given scripts.
    /// Each script is emitted as a <c>&lt;script name="..."&gt;</c> element; when the script has a
    /// parameter schema it is wrapped in a nested <c>&lt;parameters_schema&gt;</c> element, otherwise a
    /// self-closing <c>&lt;script&gt;</c> element is used. When the list is empty, a self-closing
    /// <c>&lt;available_scripts /&gt;</c> element is returned. This block lets the model know which scripts
    /// can be called and how to format their arguments (or that there are none) so it does not hallucinate script names.
    /// </summary>
    /// <param name="scripts">The scripts to include in the block.</param>
    /// <returns>
    /// An XML string starting with <c>\n&lt;available_scripts&gt;</c>, or <c>\n&lt;available_scripts /&gt;</c> if the list is empty.
    /// </returns>
    public static string BuildAvailableScriptsBlock(IReadOnlyList<AgentSkillScript> scripts)
    {
        _ = Throw.IfNull(scripts);

        if (scripts.Count == 0)
        {
            // Emit an empty element so the model knows no scripts are available and does not hallucinate script names.
            return "\n<available_scripts />";
        }

        var sb = new StringBuilder();
        sb.Append("\n<available_scripts>\n");

        foreach (var script in scripts)
        {
            var parametersSchema = script.ParametersSchema;
            var nameAttr = $"name=\"{EscapeXmlString(script.Name)}\"";
            var descAttr = !string.IsNullOrWhiteSpace(script.Description)
                ? $" description=\"{EscapeXmlString(script.Description)}\""
                : string.Empty;

            if (parametersSchema is null)
            {
                sb.Append($"  <script {nameAttr}{descAttr}/>\n");
            }
            else
            {
                sb.Append($"  <script {nameAttr}{descAttr}>\n");
                sb.Append($"    <parameters_schema>{EscapeXmlString(parametersSchema.Value.GetRawText(), preserveQuotes: true)}</parameters_schema>\n");
                sb.Append("  </script>\n");
            }
        }

        sb.Append("</available_scripts>");

        return sb.ToString();
    }

    /// <summary>
    /// Escapes XML special characters: always escapes <c>&amp;</c>, <c>&lt;</c>, <c>&gt;</c>,
    /// <c>&quot;</c>, and <c>&apos;</c>. When <paramref name="preserveQuotes"/> is <see langword="true"/>,
    /// quotes are left unescaped to preserve readability of embedded content such as JSON.
    /// </summary>
    /// <param name="value">The string to escape.</param>
    /// <param name="preserveQuotes">
    /// When <see langword="true"/>, leaves <c>"</c> and <c>'</c> unescaped for use in XML element content (e.g., JSON).
    /// When <see langword="false"/> (default), escapes all XML special characters including quotes.
    /// </param>
    private static string EscapeXmlString(string value, bool preserveQuotes = false)
    {
        var result = value
            .Replace("&", "&amp;")
            .Replace("<", "&lt;")
            .Replace(">", "&gt;");

        if (!preserveQuotes)
        {
            result = result
                .Replace("\"", "&quot;")
                .Replace("'", "&apos;");
        }

        return result;
    }
}
