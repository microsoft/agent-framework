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
    /// Builds the complete skill content containing name, description, instructions, and script parameter schemas.
    /// </summary>
    /// <param name="name">The skill name.</param>
    /// <param name="description">The skill description.</param>
    /// <param name="instructions">The raw instructions text.</param>
    /// <param name="scripts">Optional scripts associated with the skill.</param>
    /// <returns>An XML-structured content string.</returns>
    public static string Build(
        string name,
        string description,
        string instructions,
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

        if (scripts is { Count: > 0 })
        {
            sb.Append('\n');
            sb.Append(BuildScriptSchemasBlock(scripts));
        }

        return sb.ToString();
    }

    /// <summary>
    /// Builds a <c>&lt;script_schemas&gt;...&lt;/script_schemas&gt;</c> XML block for the given scripts.
    /// Each script is emitted as a <c>&lt;schema script="..."&gt;</c> element containing only
    /// the parameter schema. This block serves as a reference for the model to know how to
    /// format arguments when calling scripts, not as a discovery mechanism.
    /// </summary>
    /// <param name="scripts">The scripts to include in the block.</param>
    /// <returns>An XML string starting with <c>\n&lt;script_schemas&gt;</c>, or an empty string if the list is empty.</returns>
    public static string BuildScriptSchemasBlock(IReadOnlyList<AgentSkillScript> scripts)
    {
        _ = Throw.IfNull(scripts);

        if (scripts.Count == 0)
        {
            return string.Empty;
        }

        var sb = new StringBuilder();
        sb.Append("\n<script_schemas>\n");

        foreach (var script in scripts)
        {
            var parametersSchema = script.ParametersSchema;

            if (parametersSchema is null)
            {
                sb.Append($"  <schema script=\"{EscapeXmlString(script.Name)}\"/>\n");
            }
            else
            {
                sb.Append($"  <schema script=\"{EscapeXmlString(script.Name)}\">{EscapeXmlString(parametersSchema.Value.GetRawText(), preserveQuotes: true)}</schema>\n");
            }
        }

        sb.Append("</script_schemas>");

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
