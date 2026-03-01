// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides access to loaded skills and the skill loader for use by <see cref="FileAgentSkillScriptExecutor"/> implementations.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileAgentSkillScriptExecutionContext
{
    /// <summary>
    /// Initializes a new instance of the <see cref="FileAgentSkillScriptExecutionContext"/> class.
    /// </summary>
    /// <param name="skills">The loaded skills dictionary.</param>
    /// <param name="loader">The skill loader for reading resources.</param>
    internal FileAgentSkillScriptExecutionContext(Dictionary<string, FileAgentSkill> skills, FileAgentSkillLoader loader)
    {
        this.Skills = skills;
        this.Loader = loader;
    }

    /// <summary>
    /// Gets the loaded skills keyed by name.
    /// </summary>
    public IReadOnlyDictionary<string, FileAgentSkill> Skills { get; }

    /// <summary>
    /// Gets the skill loader for reading resources.
    /// </summary>
    public FileAgentSkillLoader Loader { get; }
}
