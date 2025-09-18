// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Linq;
using Microsoft.Bot.ObjectModel;
using Microsoft.PowerFx;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class TemplateExtensions
{
    public static string Format(this RecalcEngine engine, IEnumerable<TemplateLine> template) =>
        string.Concat(template.Select(engine.Format));

    public static string Format(this RecalcEngine engine, TemplateLine? line) =>
        line is not null ?
            string.Concat(line.Segments.Select(engine.Format)) :
            string.Empty;

    public static string Format(this RecalcEngine engine, TemplateSegment segment)
    {
        if (segment is TextSegment textSegment)
        {
            return textSegment.Value ?? string.Empty;
        }

        if (segment is ExpressionSegment { Expression: not null } expressionSegment)
        {
            if (expressionSegment.Expression.ExpressionText is not null)
            {
                return engine.Eval(expressionSegment.Expression.ExpressionText).Format();
            }

            if (expressionSegment.Expression.VariableReference is not null)
            {
                return engine.Eval(expressionSegment.Expression.VariableReference.ToString()).Format();
            }
        }

        throw new DeclarativeModelException($"Unsupported segment type: {segment.GetType().Name}");
    }
}
