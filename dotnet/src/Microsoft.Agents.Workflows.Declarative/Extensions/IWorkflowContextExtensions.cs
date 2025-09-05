// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

/// <summary>
/// Extension methods for <see cref="IWorkflowContext"/> that assist with
/// Power Fx expression evaluation.
/// </summary>
public static class IWorkflowContextExtensions
{
    /// <summary>
    /// Formats one or more template lines by restoring the workflow's declarative state
    /// and evaluating any embedded expressions (e.g., Power Fx) contained within each line.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="lines">The template lines to format.</param>
    /// <returns>
    /// A single string containing the formatted results of all lines separated by newline characters.
    /// A trailing newline will be present if at least one line was processed.
    /// </returns>
    /// <example>
    /// Example:
    /// var text = await context.FormatAsync("Hello @{User.Name}", "Count: @{Metrics.Count}");
    /// </example>
    public static async ValueTask<string> FormatAsync(this IWorkflowContext context, params string[] lines)
    {
        DeclarativeWorkflowState state = new(RecalcEngineFactory.Create());
        await state.RestoreAsync(context, cancellationToken: default).ConfigureAwait(false);

        StringBuilder builder = new();
        foreach (string line in lines)
        {
            builder.AppendLine(state.Format(TemplateLine.Parse(line)));
        }

        return builder.ToString();
    }
}
