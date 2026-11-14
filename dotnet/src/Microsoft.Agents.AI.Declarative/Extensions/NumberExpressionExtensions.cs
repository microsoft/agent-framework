// Copyright (c) Microsoft. All rights reserved.

using System.Globalization;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.ObjectModel;

/// <summary>
/// Extension methods for <see cref="NumberExpression"/>.
/// </summary>
internal static class NumberExpressionExtensions
{
    /// <summary>
    /// Evaluates the given <see cref="NumberExpression"/> using the provided <see cref="RecalcEngine"/>.
    /// </summary>
    /// <param name="expression">Expression to evaluate.</param>
    /// <param name="engine">Recalc engine to use for evaluation.</param>
    /// <param name="cancellationToken">Cancellation token to observe while evaluating the expression.</param>
    /// <returns>The evaluated number value, or null if the expression is null or cannot be evaluated.</returns>
    internal static async Task<double?> EvalAsync(this NumberExpression? expression, RecalcEngine? engine, CancellationToken cancellationToken = default)
    {
        if (expression is null)
        {
            return null;
        }

        if (expression.IsLiteral)
        {
            return expression.LiteralValue;
        }

        if (engine is null)
        {
            return null;
        }

        if (expression.IsExpression)
        {
            return (await engine.EvalAsync(expression.ExpressionText!, cancellationToken).ConfigureAwait(false)).AsDouble();
        }
        else if (expression.IsVariableReference)
        {
            var formulaValue = await engine.EvalAsync(expression.VariableReference!.VariableName, cancellationToken).ConfigureAwait(false);
            if (formulaValue is NumberValue numberValue)
            {
                return numberValue.Value;
            }

            if (formulaValue is StringValue stringValue && double.TryParse(stringValue.Value, NumberStyles.Float, CultureInfo.InvariantCulture, out double result))
            {
                return result;
            }
        }

        return null;
    }
}
