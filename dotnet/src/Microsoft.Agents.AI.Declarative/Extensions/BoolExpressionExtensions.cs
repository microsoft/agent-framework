// Copyright (c) Microsoft. All rights reserved.

using System.Threading;
using System.Threading.Tasks;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.ObjectModel;

/// <summary>
/// Extension methods for <see cref="BoolExpression"/>.
/// </summary>
internal static class BoolExpressionExtensions
{
    /// <summary>
    /// Evaluates the given <see cref="BoolExpression"/> using the provided <see cref="RecalcEngine"/>.
    /// </summary>
    /// <param name="expression">Expression to evaluate.</param>
    /// <param name="engine">Recalc engine to use for evaluation.</param>
    /// <param name="cancellationToken">Cancellation token to observe while evaluating the expression.</param>
    /// <returns>The evaluated boolean value, or null if the expression is null or cannot be evaluated.</returns>
    internal static async Task<bool?> EvalAsync(this BoolExpression? expression, RecalcEngine? engine, CancellationToken cancellationToken = default)
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
            return (await engine.EvalAsync(expression.ExpressionText!, cancellationToken).ConfigureAwait(false)).AsBoolean();
        }
        else if (expression.IsVariableReference)
        {
            var formulaValue = await engine.EvalAsync(expression.VariableReference!.VariableName, cancellationToken).ConfigureAwait(false);
            if (formulaValue is BooleanValue booleanValue)
            {
                return booleanValue.Value;
            }

            if (formulaValue is StringValue stringValue && bool.TryParse(stringValue.Value, out bool result))
            {
                return result;
            }
        }

        return null;
    }
}
