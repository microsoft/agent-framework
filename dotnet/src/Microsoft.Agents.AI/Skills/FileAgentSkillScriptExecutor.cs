// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;

namespace Microsoft.Agents.AI;

/// <summary>
/// Defines the contract for skill script execution modes.
/// </summary>
/// <remarks>
/// <para>
/// A <see cref="FileAgentSkillScriptExecutor"/> provides the instructions and tools needed to enable
/// script execution within an agent skill. Concrete implementations determine how scripts
/// are executed (e.g., via the LLM's hosted code interpreter, an external executor, or a hybrid approach).
/// </para>
/// <para>
/// Use the static factory methods to create instances:
/// <list type="bullet">
/// <item><description><see cref="HostedCodeInterpreter"/> — executes scripts using the LLM provider's built-in code interpreter.</description></item>
/// </list>
/// </para>
/// </remarks>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public abstract class FileAgentSkillScriptExecutor
{
    /// <summary>
    /// Creates a <see cref="FileAgentSkillScriptExecutor"/> that uses the LLM provider's hosted code interpreter for script execution.
    /// </summary>
    /// <returns>A <see cref="FileAgentSkillScriptExecutor"/> instance configured for hosted code interpreter execution.</returns>
    public static FileAgentSkillScriptExecutor HostedCodeInterpreter() => new HostedCodeInterpreterFileAgentSkillScriptExecutor();

    /// <summary>
    /// Returns the tools and instructions contributed by this executor.
    /// </summary>
    /// <param name="context">
    /// The execution context provided by the skills provider, containing the loaded skills
    /// and the skill loader for reading resources.
    /// </param>
    /// <returns>A <see cref="FileAgentSkillScriptExecutionDetails"/> containing the executor's tools and instructions.</returns>
    protected internal abstract FileAgentSkillScriptExecutionDetails GetExecutionDetails(FileAgentSkillScriptExecutionContext context);
}
