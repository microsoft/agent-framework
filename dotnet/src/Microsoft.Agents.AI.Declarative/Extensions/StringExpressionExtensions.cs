// Copyright (c) Microsoft. All rights reserved.

using Microsoft.PowerFx;
using Microsoft.PowerFx.Types;

namespace Microsoft.Bot.ObjectModel;

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
    /// <returns>The evaluated string value, or null if the expression is null or cannot be evaluated.</returns>
    public static string? Eval(this StringExpression? expression, RecalcEngine? engine)
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
            return engine.Eval(expression.ExpressionText!).ToString();
        }
        else if (expression.IsVariableReference)
        {
            var stringValue = engine.Eval(expression.VariableReference!.VariableName) as StringValue;
            return stringValue?.Value;
        }

        return null;
    }
}
