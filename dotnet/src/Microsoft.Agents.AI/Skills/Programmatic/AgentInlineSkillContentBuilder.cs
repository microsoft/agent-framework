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
    /// Builds the complete skill content containing name, description, instructions, resources, and scripts.
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

        if (resources is { Count: > 0 })
        {
            sb.Append("\n\n<resources>\n");
            foreach (var resource in resources)
            {
                if (resource.Description is not null)
                {
                    sb.Append($"  <resource name=\"{EscapeXmlString(resource.Name)}\" description=\"{EscapeXmlString(resource.Description)}\"/>\n");
                }
                else
                {
                    sb.Append($"  <resource name=\"{EscapeXmlString(resource.Name)}\"/>\n");
                }
            }

            sb.Append("</resources>");
        }

        if (scripts is { Count: > 0 })
        {
            sb.Append('\n');
            sb.Append(BuildScriptsBlock(scripts));
        }

        return sb.ToString();
    }

    /// <summary>
    /// Builds a <c>&lt;scripts&gt;...&lt;/scripts&gt;</c> XML block for the given scripts.
    /// Each script is emitted as a <c>&lt;script name="..."&gt;</c> element with optional
    /// <c>description</c> attribute and <c>&lt;parameters_schema&gt;</c> child element.
    /// </summary>
    /// <param name="scripts">The scripts to include in the block.</param>
    /// <returns>An XML string starting with <c>\n&lt;scripts&gt;</c>, or an empty string if the list is empty.</returns>
    public static string BuildScriptsBlock(IReadOnlyList<AgentSkillScript> scripts)
    {
        _ = Throw.IfNull(scripts);

        if (scripts.Count == 0)
        {
            return string.Empty;
        }

        var sb = new StringBuilder();
        sb.Append("\n<scripts>\n");

        foreach (var script in scripts)
        {
            var parametersSchema = script.ParametersSchema;

            if (script.Description is null && parametersSchema is null)
            {
                sb.Append($"  <script name=\"{EscapeXmlString(script.Name)}\"/>\n");
            }
            else
            {
                sb.Append(script.Description is not null
                    ? $"  <script name=\"{EscapeXmlString(script.Name)}\" description=\"{EscapeXmlString(script.Description)}\">\n"
                    : $"  <script name=\"{EscapeXmlString(script.Name)}\">\n");

                if (parametersSchema is not null)
                {
                    sb.Append($"    <parameters_schema>{EscapeXmlString(parametersSchema.Value.GetRawText(), preserveQuotes: true)}</parameters_schema>\n");
                }

                sb.Append("  </script>\n");
            }
        }

        sb.Append("</scripts>");

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
