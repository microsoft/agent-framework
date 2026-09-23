// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.ObjectModel;

/// <summary>
/// Extension methods for <see cref="StringExpression"/>.
/// </summary>
public static class StringExpressionExtensions
{
    /// <summary>
    /// Evaluates the given <see cref="StringExpression"/> using the provided <see cref="RecalcEngine"/>.
    /// </summary>
    /// <param name="expression">Expression to evaluate.</param>
    /// <param name="engine">Recalc engine to use for evaluation.</param>
    /// <param name="cancellationToken">Cancellation token to use for the asynchronous operation.</param>
    /// <returns>The evaluated string value, or null if the expression is null or cannot be evaluated.</returns>
    public static async Task<string?> EvalAsync(this StringExpression? expression, RecalcEngine? engine, CancellationToken cancellationToken = default)
    {
        if (expression is null)
        {
            return null;
        }

        if (expression.IsLiteral)
        {
            return expression.LiteralValue?.ToString();
        }

        if (engine is null)
        {
            return null;
        }

        if (expression.IsExpression)
        {
            return (await engine.EvalAsync(expression.ExpressionText!, cancellationToken: cancellationToken).ConfigureAwait(false)).ToString();
        }
        else if (expression.IsVariableReference)
        {
            var stringValue = await engine.EvalAsync(expression.VariableReference!.VariableName, cancellationToken: cancellationToken).ConfigureAwait(false) as StringValue;
            return stringValue?.Value;
        }

        return null;
    }
}
