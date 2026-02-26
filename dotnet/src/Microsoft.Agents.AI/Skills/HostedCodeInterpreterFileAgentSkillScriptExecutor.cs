// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="FileAgentSkillScriptExecutor"/> that uses the LLM provider's hosted code interpreter for script execution.
/// </summary>
/// <remarks>
/// This executor directs the LLM to load scripts via <c>read_skill_resource</c> and execute them
/// using the provider's built-in code interpreter. A <see cref="HostedCodeInterpreterTool"/> is
/// registered to signal the provider to enable its code interpreter sandbox.
/// </remarks>
internal sealed class HostedCodeInterpreterFileAgentSkillScriptExecutor : FileAgentSkillScriptExecutor
{
    private static readonly FileAgentSkillScriptExecutionDetails s_contribution = new()
    {
        Instructions =
            """

            Some skills include executable scripts (e.g., Python files) in their resources.
            When a skill's instructions reference a script:
            1. Use `read_skill_resource` to load the script content
            2. Execute the script using the code interpreter

            """,
        Tools = [new HostedCodeInterpreterTool()],
    };

    /// <inheritdoc />
#pragma warning disable RCS1168 // Parameter name differs from base name
    protected internal override FileAgentSkillScriptExecutionDetails GetExecutionDetails(FileAgentSkillScriptExecutionContext _) => s_contribution;
#pragma warning restore RCS1168 // Parameter name differs from base name
}
