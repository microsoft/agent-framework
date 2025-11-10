// Copyright (c) Microsoft. All rights reserved.

using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI.Workflows;

internal static partial class AIAgentExtensions
{
    /// <summary>
    /// Derives from an agent a unique but also hopefully descriptive name that can be used as an executor's
    /// name or in a function name.
    /// </summary>
    public static string GetDescriptiveId(this AIAgent agent)
    {
        string id = string.IsNullOrEmpty(agent.Name) ? agent.Id : $"{agent.Name}_{agent.Id}";
        return InvalidNameCharsRegex().Replace(id, "_");
    }

    /// <summary>
    /// Regex that flags any character other than ASCII digits or letters or the underscore.
    /// </summary>
#if NET
    [GeneratedRegex("[^0-9A-Za-z]+")]
    private static partial Regex InvalidNameCharsRegex();
#else
    private static Regex InvalidNameCharsRegex() => s_invalidNameCharsRegex;
    private static readonly Regex s_invalidNameCharsRegex = new("[^0-9A-Za-z_]+", RegexOptions.Compiled);
#endif
}
