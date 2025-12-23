// Copyright (c) Microsoft. All rights reserved.

using System.Globalization;
using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Bot.ObjectModel;

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
    /// <returns>The evaluated number value, or null if the expression is null or cannot be evaluated.</returns>
    internal static double? Eval(this NumberExpression? expression, RecalcEngine? engine)
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
            return engine.Eval(expression.ExpressionText!).AsDouble();
        }
        else if (expression.IsVariableReference)
        {
            var formulaValue = engine.Eval(expression.VariableReference!.VariableName);
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
