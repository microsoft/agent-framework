// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using Microsoft.Shared.DiagnosticIds;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Hosting.OpenAI;

/// <summary>
/// Configures the dangerous forwarding of client-provided function declarations.
/// </summary>
[Experimental(DiagnosticIds.Experiments.AgentsAIExperiments)]
public sealed class OpenAIClientFunctionToolsOptions
{
    /// <summary>
    /// Initializes a new instance of the <see cref="OpenAIClientFunctionToolsOptions"/> class.
    /// </summary>
    /// <param name="nameConflictBehavior">
    /// The required behavior when a client function uses the same name as a hosted agent tool.
    /// </param>
    public OpenAIClientFunctionToolsOptions(OpenAIClientFunctionToolNameConflictBehavior nameConflictBehavior)
    {
        this.NameConflictBehavior = Throw.IfNull(nameConflictBehavior);
    }

    /// <summary>
    /// Gets the behavior used when a client function uses the same name as a hosted agent tool.
    /// </summary>
    public OpenAIClientFunctionToolNameConflictBehavior NameConflictBehavior { get; }
}
