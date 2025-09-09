// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.PowerFx;
using Microsoft.Bot.ObjectModel;
using Microsoft.Bot.ObjectModel.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.Kit;

/// <summary>
/// Extension methods for <see cref="IWorkflowContext"/> that assist with
/// Power Fx expression evaluation.
/// </summary>
public static class IWorkflowContextExtensions
{
    /// <summary>
    /// Formats a template lines using the workflow's declarative state
    /// and evaluating any embedded expressions (e.g., Power Fx) contained within each line.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="line">The template line to format.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>
    /// A single string containing the formatted results of all lines separated by newline characters.
    /// A trailing newline will be present if at least one line was processed.
    /// </returns>
    /// <example>
    /// Example:
    /// var text = await context.FormatAsync("Hello @{User.Name}", "Count: @{Metrics.Count}");
    /// </example>
    public static ValueTask<string> FormatTemplateAsync(this IWorkflowContext context, string line, CancellationToken cancellationToken = default) =>
        context.FormatTemplateAsync([line], cancellationToken);

    /// <summary>
    /// Formats a template lines using the workflow's declarative state
    /// and evaluating any embedded expressions (e.g., Power Fx) contained within each line.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="lines">The template lines to format.</param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>
    /// A single string containing the formatted results of all lines separated by newline characters.
    /// A trailing newline will be present if at least one line was processed.
    /// </returns>
    /// <example>
    /// Example:
    /// var text = await context.FormatAsync("Hello @{User.Name}", "Count: @{Metrics.Count}");
    /// </example>
    public static async ValueTask<string> FormatTemplateAsync(this IWorkflowContext context, IEnumerable<string> lines, CancellationToken cancellationToken = default)
    {
        WorkflowFormulaState state = await context.GetStateAsync(cancellationToken: default).ConfigureAwait(false);

        StringBuilder builder = new();
        foreach (string line in lines)
        {
            builder.AppendLine(state.Engine.Format(TemplateLine.Parse(line)));
        }

        return builder.ToString();
    }

    /// <summary>
    /// Evaluate an expression using the workflow's declarative state.
    /// </summary>
    /// <param name="context">The workflow execution context used to restore persisted state prior to formatting.</param>
    /// <param name="expression"></param>
    /// <param name="cancellationToken">A token that propagates notification when operation should be canceled.</param>
    /// <returns>The evaluated expression value</returns>
    public static async ValueTask<object?> EvaluateExpressionAsync(this IWorkflowContext context, string expression, CancellationToken cancellationToken = default)
    {
        WorkflowFormulaState state = await context.GetStateAsync(cancellationToken).ConfigureAwait(false);

        EvaluationResult<DataValue> result = state.Evaluator.GetValue(ValueExpression.Expression(expression));

        return result.Value.ToObject();
    }
}
