// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using System.Globalization;
using Microsoft.PowerFx.Types;

namespace Microsoft.Agents.AI.Workflows.Declarative.Extensions;

internal static class StringExtensions
{
    private const string JsonDelimiter = "```";

    public static string TrimJsonDelimiter(this string value)
    {
        value = value.Trim();

        // Scan linearly so malformed fenced input cannot trigger regex backtracking.
        int openingDelimiterIndex = FindOpeningDelimiter(value);
        if (openingDelimiterIndex < 0)
        {
            return value;
        }

        int contentIndex = openingDelimiterIndex + JsonDelimiter.Length;
        while (contentIndex < value.Length && IsWordCharacter(value[contentIndex]))
        {
            contentIndex++;
        }

        while (contentIndex < value.Length && char.IsWhiteSpace(value[contentIndex]))
        {
            contentIndex++;
        }

        int closingDelimiterIndex = FindClosingDelimiter(value, contentIndex);
        return closingDelimiterIndex < 0 ?
            value :
            value.Substring(contentIndex, closingDelimiterIndex - contentIndex).Trim();
    }

    public static FormulaValue ToFormula(this string? value) =>
        string.IsNullOrWhiteSpace(value) ? FormulaValue.NewBlank() : FormulaValue.New(value);

    public static string FormatType(this string identifier) => FormatIdentifier(identifier);

    public static string FormatName(this string identifier) => FormatIdentifier(identifier, skipFirst: true);

    private static int FindOpeningDelimiter(string value)
    {
        for (int index = 0; index <= value.Length - JsonDelimiter.Length; index++)
        {
            if ((index == 0 || value[index - 1] == '\n') && IsDelimiterAt(value, index))
            {
                return index;
            }
        }

        return -1;
    }

    private static int FindClosingDelimiter(string value, int startIndex)
    {
        for (int index = startIndex; index <= value.Length - JsonDelimiter.Length; index++)
        {
            if (IsDelimiterAt(value, index) && IsLineEnd(value, index + JsonDelimiter.Length))
            {
                return index;
            }
        }

        return -1;
    }

    private static bool IsDelimiterAt(string value, int index) =>
        value[index] == '`' &&
        value[index + 1] == '`' &&
        value[index + 2] == '`';

    private static bool IsLineEnd(string value, int index) =>
        index == value.Length ||
        value[index] == '\n' ||
        (value[index] == '\r' && index + 1 < value.Length && value[index + 1] == '\n');

    // Keep language qualifier handling compatible with .NET regex \w semantics.
    private static bool IsWordCharacter(char value) =>
        char.GetUnicodeCategory(value) is
            UnicodeCategory.UppercaseLetter or
            UnicodeCategory.LowercaseLetter or
            UnicodeCategory.TitlecaseLetter or
            UnicodeCategory.ModifierLetter or
            UnicodeCategory.OtherLetter or
            UnicodeCategory.NonSpacingMark or
            UnicodeCategory.DecimalDigitNumber or
            UnicodeCategory.ConnectorPunctuation;

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
