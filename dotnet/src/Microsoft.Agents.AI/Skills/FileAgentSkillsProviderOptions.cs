// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Configuration options for <see cref="FileAgentSkillsProvider"/>.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class FileAgentSkillsProviderOptions
{
    /// <summary>
    /// Gets or sets a custom system prompt template for advertising skills.
    /// Use <c>{0}</c> as the placeholder for the generated skills list.
    /// When <see langword="null"/>, a default template is used.
    /// </summary>
    public string? SkillsInstructionPrompt { get; set; }

    /// <summary>
    /// Gets or sets the file extensions recognized as discoverable skill resources.
    /// Each value must start with a <c>'.'</c> character (for example, <c>.md</c>), and
    /// extension comparisons are performed in a case-insensitive manner.
    /// Files in the skill directory (and its subdirectories) whose extension matches
    /// one of these values will be automatically discovered as resources.
    /// When <see langword="null"/>, a default set of extensions is used
    /// (<c>.md</c>, <c>.json</c>, <c>.yaml</c>, <c>.yml</c>, <c>.csv</c>, <c>.xml</c>, <c>.txt</c>).
    /// </summary>
    public IEnumerable<string>? AllowedResourceExtensions { get; set; }
}
