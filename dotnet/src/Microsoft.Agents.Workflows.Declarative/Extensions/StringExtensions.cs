// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Globalization;
using System.Text.RegularExpressions;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.Workflows.Declarative.Extensions;

internal static class StringExtensions
{
    private static readonly Regex s_regex = new(@"^```(?:\w*)\s*([\s\S]*?)\s*```$", RegexOptions.Compiled | RegexOptions.Multiline);

    public static string TrimJsonDelimiter(this string value)
    {
        Match match = s_regex.Match(value.Trim());
        if (match.Success)
        {
            return match.Groups[1].Value.Trim();
        }

        return value.Trim();
    }

    public static FormulaValue ToFormula(this string? value) =>
        string.IsNullOrWhiteSpace(value) ? FormulaValue.NewBlank() : FormulaValue.New(value);

    public static string FormatType(this string identifier) => FormatIdentifier(identifier);

    public static string FormatName(this string identifier) => FormatIdentifier(identifier, skipFirst: true);

    private static string FormatIdentifier(string identifier, bool skipFirst = false)
    {
        string[] words = identifier.Split('_');

        // Capitalize each word
        for (int index = skipFirst ? 1 : 0; index < words.Length; ++index)
        {
            words[index] = CultureInfo.CurrentCulture.TextInfo.ToTitleCase(words[index]);
        }

        // Combine the words and return
        return string.Concat(words);
    }

    public static IEnumerable<string> ByLine(this string source)
    {
        foreach (string line in source.Trim().Split('\n'))
        {
            yield return line.TrimEnd();
        }
    }
}
