// Copyright (c) Microsoft. All rights reserved.

using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI.Workflows;

internal static partial class AIAgentExtensions
{
    private const int GuidSuffixLength = 8;

    /// <summary>
    /// Derives from an agent a unique but also hopefully descriptive name that can be used as an executor's
    /// name or in a function name.
    /// </summary>
    /// <remarks>
    /// The ID format is "{Name}_{GuidSuffix}" where Name is the agent's name if provided,
    /// otherwise the agent's type name. GuidSuffix is the first 8 characters of the agent's unique ID
    /// to ensure uniqueness while maintaining readability.
    /// </remarks>
    public static string GetDescriptiveId(this AIAgent agent)
    {
        string name = string.IsNullOrEmpty(agent.Name)
            ? agent.GetType().Name
            : agent.Name;

        // Use first 8 characters of the GUID for uniqueness while keeping the ID readable
        string guidSuffix = agent.Id.Length > GuidSuffixLength
            ? agent.Id.Substring(0, GuidSuffixLength)
            : agent.Id;

        string id = $"{name}_{guidSuffix}";
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
