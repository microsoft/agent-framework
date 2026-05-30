// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text;
using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI;

/// <summary>
/// Provides utility methods for fixing common JSON malformations
/// that can arise when consuming JSON output from LLMs.
/// </summary>
internal static class JsonFixer
{
    /// <summary>
    /// Attempts to fix common JSON malformations in the provided text.
    /// </summary>
    /// <param name="text">The raw text potentially containing JSON.</param>
    /// <param name="fixedText">The repaired JSON text, or the original if no fix was needed.</param>
    /// <returns><see langword="true"/> if a fix was applied; <see langword="false"/> if the text was already valid or no fix was possible.</returns>
    public static bool TryFix([NotNullWhen(true)] string? text, out string? fixedText)
    {
        if (string.IsNullOrEmpty(text))
        {
            fixedText = null;
            return false;
        }

        string result = text;

        bool changed = TryStripMarkdownFences(ref result)
            | TryFixTrailingCommas(ref result)
            | TryFixTruncatedJson(ref result)
            | TryUnstringifyNestedJson(ref result);

        fixedText = changed ? result : null;
        return changed;
    }

    /// <summary>
    /// Removes markdown code fences (e.g. ```json ... ```) from the text.
    /// </summary>
    public static bool TryStripMarkdownFences(ref string text)
    {
        const string FenceMarker = "```";
        int start = text.IndexOf(FenceMarker, StringComparison.Ordinal);
        if (start < 0)
        {
            return false;
        }

        // Find the end of the fence line (the newline after the opening fence)
        int fenceEnd = text.IndexOf('\n', start);
        if (fenceEnd < 0)
        {
            // ``` at start but no newline — treat rest as code
            text = text[(start + 3)..].Trim();
            return true;
        }

        int contentStart = fenceEnd + 1;

        // Find closing fence
        int closeFence = text.LastIndexOf(FenceMarker, StringComparison.Ordinal);
        if (closeFence >= contentStart)
        {
            // Extract content between fences
            text = text[contentStart..closeFence].Trim();
        }
        else
        {
            // No closing fence — treat rest as code
            text = text[contentStart..].Trim();
        }

        return true;
    }

    /// <summary>
    /// Removes trailing commas before '}', ']', or at the end of the string.
    /// </summary>
    public static bool TryFixTrailingCommas(ref string text)
    {
        string original = text;

        // Remove trailing comma before closing brace/bracket
        text = Regex.Replace(text, @",(\s*[}\]])", "$1");

        // Remove trailing comma at end of string (truncated after comma)
        text = Regex.Replace(text, @",\s*$", "");

        return text != original;
    }

    /// <summary>
    /// Attempts to complete a truncated JSON payload by adding missing closing brackets,
    /// braces, and quotes.
    /// </summary>
    public static bool TryFixTruncatedJson(ref string text)
    {
        string original = text;
        var stack = new Stack<char>();
        bool inString = false;
        bool escaped = false;

        foreach (char c in text)
        {
            if (inString)
            {
                if (escaped)
                {
                    escaped = false;
                }
                else if (c == '\\')
                {
                    escaped = true;
                }
                else if (c == '"')
                {
                    inString = false;
                }
            }
            else
            {
                switch (c)
                {
                    case '{':
                    case '[':
                        stack.Push(c);
                        break;
                    case '}':
                        if (stack.Count > 0 && stack.Peek() == '{')
                        {
                            stack.Pop();
                        }
                        break;
                    case ']':
                        if (stack.Count > 0 && stack.Peek() == '[')
                        {
                            stack.Pop();
                        }
                        break;
                    case '"':
                        inString = true;
                        break;
                }
            }
        }

        // Close any unclosed string
        if (inString)
        {
            text += '"';
        }

        // Close any unclosed brackets/braces
        while (stack.Count > 0)
        {
            text += stack.Pop() switch
            {
                '{' => '}',
                '[' => ']',
                _ => string.Empty
            };
        }

        return text != original;
    }

    /// <summary>
    /// Detects and un-stringifies nested JSON objects that have been embedded
    /// as escaped string values (e.g. <c>"arguments": "{\"key\": \"value\"}"</c>
    /// becomes <c>"arguments": {"key": "value"}</c>).
    /// </summary>
    public static bool TryUnstringifyNestedJson(ref string text)
    {
        string original = text;

        // Match pattern: "propertyName": "{...}" or "propertyName": "{\\...}"
        text = Regex.Replace(
            text,
            @"\""(\w+)\\"":\s*\""(\{.*?\})\""",
            m =>
            {
                string propertyName = m.Groups[1].Value;
                string potentialJson = m.Groups[2].Value;

                // Unescape the string
                potentialJson = Regex.Unescape(potentialJson);

                // Check if it's valid JSON
                try
                {
                    System.Text.Json.JsonDocument.Parse(potentialJson);
                    // It's valid JSON, so use it directly
                    return $"\"{propertyName}\": {potentialJson}";
                }
                catch
                {
                    // Not valid JSON, keep original
                    return m.Value;
                }
            });

        return text != original;
    }
}
