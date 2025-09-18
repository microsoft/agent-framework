// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Runtime.CompilerServices;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Text.RegularExpressions;

namespace Microsoft.Agents.Workflows.Checkpointing;

/// <summary>
/// Provides support for using <see cref="ScopeKey"/> values as dictionary keys when serializing and deserializing JSON.
/// </summary>
internal sealed class ScopeKeyConverter : JsonConverterDictionarySupportBase<ScopeKey>
{
    protected override JsonTypeInfo<ScopeKey> TypeInfo => WorkflowsJsonUtilities.JsonContext.Default.ScopeKey;

    public static readonly Regex ScopeKeyPropertyNamePattern =
        new(@"^(?<executorId>(((\|\|)|([^\|]))*))\|(?<scopeName>(@(((\|\|)|([^\|]))*))?)\|(?<key>(((\|\|)|([^\|]))*)?)$",
        RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.ExplicitCapture);

    protected override ScopeKey Parse(string propertyName)
    {
        Match scopeKeyPatternMatch = ScopeKeyPropertyNamePattern.Match(propertyName);
        if (!scopeKeyPatternMatch.Success)
        {
            throw new JsonException($"Invalid ScopeKey property name format. Got '{propertyName}'.");
        }

        string executorId = scopeKeyPatternMatch.Groups["executorId"].Value;
        string scopeName = scopeKeyPatternMatch.Groups["scopeName"].Value;
        string key = scopeKeyPatternMatch.Groups["key"].Value;

        return new ScopeKey(Unescape(executorId)!,
                            Unescape(scopeName, allowNullAndPad: true),
                            Unescape(key)!);
    }

    [return: NotNull]
    private static string Escape(string? value, bool allowNullAndPad = false, [CallerArgumentExpression("value")] string componentName = "ScopeKey")
    {
        if (!allowNullAndPad && value == null)
        {
            throw new JsonException($"Invalid {componentName} '{value}'. Expecting non-null string.");
        }

        if (value == null)
        {
            return string.Empty;
        }

        if (allowNullAndPad)
        {
            return $"@{value.Replace("|", "||")}";
        }

        return $"{value.Replace("|", "||")}";
    }

    private static string? Unescape([DisallowNull] string value, bool allowNullAndPad = false, [CallerArgumentExpression("value")] string componentName = "ScopeKey")
    {
        if (value.Length == 0)
        {
            if (!allowNullAndPad)
            {
                throw new JsonException($"Invalid {componentName} '{value}'. Expecting empty string or a value that is prefixed with '@'.");
            }

            return null;
        }

        if (allowNullAndPad && value[0] != '@')
        {
            throw new JsonException($"Invalid {componentName} component '{value}'. Expecting empty string or a value that is prefixed with '@'.");
        }

        if (allowNullAndPad)
        {
            value = value.Substring(1);
        }

        return value.Replace("||", "|");
    }

    protected override string Stringify([DisallowNull] ScopeKey value)
    {
        string? executorIdEscaped = Escape(value.ScopeId.ExecutorId);
        string? scopeNameEscaped = Escape(value.ScopeId.ScopeName, allowNullAndPad: true);
        string? keyEscaped = Escape(value.Key);

        return $"{executorIdEscaped}|{scopeNameEscaped}|{keyEscaped}";
    }
}
