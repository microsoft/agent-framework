// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using System.Reflection;

namespace Microsoft.Agents.AI.UnitTests.AgentSkills;

/// <summary>
/// Test-only helpers that peek at the underlying resource list of a skill via reflection.
/// </summary>
/// <remarks>
/// The public <see cref="AgentSkill"/> API exposes resources only through
/// <see cref="AgentSkill.HasResources"/> and <see cref="AgentSkill.GetResourceAsync"/>.
/// These helpers exist purely to allow unit tests to inspect the concrete enumerated list a
/// skill carries; they intentionally use reflection so that no test-only members leak into
/// production types.
/// </remarks>
internal static class AgentSkillTestExtensions
{
    public static IReadOnlyList<AgentSkillResource>? GetTestResources(this AgentSkill skill)
    {
        // AgentClassSkill<TSelf>: "_reflectedResources" private field (lazy reflection-discovered).
        // Trigger discovery by calling HasResources first, then read the field.
        for (var type = skill.GetType(); type is not null; type = type.BaseType)
        {
            var field = type.GetField("_reflectedResources", BindingFlags.NonPublic | BindingFlags.Instance);
            if (field is not null)
            {
                // Trigger lazy discovery
                _ = skill.HasResources;
                return UnwrapList(field.GetValue(skill));
            }
        }

        // AgentFileSkill / AgentInlineSkill: private "_resources" field.
        for (var type = skill.GetType(); type is not null; type = type.BaseType)
        {
            var field = type.GetField("_resources", BindingFlags.NonPublic | BindingFlags.Instance);
            if (field is not null)
            {
                return UnwrapList(field.GetValue(skill));
            }
        }

        return null;
    }

    private static IReadOnlyList<AgentSkillResource>? UnwrapList(object? value) =>
        value switch
        {
            null => null,
            IReadOnlyList<AgentSkillResource> list => list,
            IEnumerable<AgentSkillResource> seq => seq.ToList(),
            _ => null,
        };
}
