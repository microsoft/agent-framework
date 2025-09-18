// Copyright (c) Microsoft. All rights reserved.

using System.Text.RegularExpressions;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static partial class StringExtensions
{
#if NET
    [GeneratedRegex(@"^```(?:\w*)\s*([\s\S]*?)\s*```$", RegexOptions.Multiline)]
    private static partial Regex TrimJsonDelimiterRegex();
#else
    private static Regex TrimJsonDelimiterRegex() => s_trimJsonDelimiterRegex;
    private static readonly Regex s_trimJsonDelimiterRegex = new(@"^```(?:\w*)\s*([\s\S]*?)\s*```$", RegexOptions.Compiled | RegexOptions.Multiline);
#endif

    public static string TrimJsonDelimiter(this string value)
    {
        value = value.Trim();

        Match match = TrimJsonDelimiterRegex().Match(value);
        return match.Success ?
            match.Groups[1].Value.Trim() :
            value;
    }

    public static FormulaValue ToFormula(this string? value) =>
        string.IsNullOrWhiteSpace(value) ? FormulaValue.NewBlank() : FormulaValue.New(value);
}
