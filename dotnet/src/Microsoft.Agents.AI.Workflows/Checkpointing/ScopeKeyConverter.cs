// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Provides support for using <see cref="ScopeKey"/> values as dictionary keys when serializing and deserializing JSON.
/// </summary>
internal sealed partial class ScopeKeyConverter : JsonConverterDictionarySupportBase<ScopeKey>
{
    protected override JsonTypeInfo<ScopeKey> TypeInfo => WorkflowsJsonUtilities.JsonContext.Default.ScopeKey;

    private const string ScopeKeyPropertyNamePattern = @"^(?<executorId>(((\|\|)|([^\|]))*))\|(?<scopeName>(@(((\|\|)|([^\|]))*))?)\|(?<key>(((\|\|)|([^\|]))*)?)$";
#if NET
    [GeneratedRegex(ScopeKeyPropertyNamePattern, RegexOptions.CultureInvariant | RegexOptions.ExplicitCapture)]
    public static partial Regex ScopeKeyPropertyNameRegex();
#else
    public static Regex ScopeKeyPropertyNameRegex() => s_scopeKeyPropertyNameRegex;
    private static readonly Regex s_scopeKeyPropertyNameRegex =
        new(ScopeKeyPropertyNamePattern, RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.ExplicitCapture);
#endif

    protected override ScopeKey Parse(string propertyName)
    {
        Match scopeKeyPatternMatch = ScopeKeyPropertyNameRegex().Match(propertyName);
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

    protected override string Stringify([DisallowNull] ScopeKey value)
    {
        string? executorIdEscaped = Escape(value.ScopeId.ExecutorId);
        string? scopeNameEscaped = Escape(value.ScopeId.ScopeName, allowNullAndPad: true);
        string? keyEscaped = Escape(value.Key);

        return $"{executorIdEscaped}|{scopeNameEscaped}|{keyEscaped}";
    }
}
