// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics.CodeAnalysis;
using System.Text.Json;
using System.Text.Json.Serialization.Metadata;
using System.Text.RegularExpressions;

namespace Microsoft.Agents.AI.Workflows.Checkpointing;

/// <summary>
/// Provides support for using <see cref="CheckpointInfo"/> values as dictionary keys when serializing and deserializing JSON.
/// </summary>
internal sealed partial class CheckpointInfoConverter() : JsonConverterDictionarySupportBase<CheckpointInfo>
{
    protected override JsonTypeInfo<CheckpointInfo> TypeInfo
        => WorkflowsJsonUtilities.JsonContext.Default.CheckpointInfo;

    private const string CheckpointInfoPropertyNamePattern = @"^(?<runId>(((\|\|)|([^\|]))*))\|(?<checkpointId>(((\|\|)|([^\|]))*)?)$";
#if NET
    [GeneratedRegex(CheckpointInfoPropertyNamePattern, RegexOptions.CultureInvariant | RegexOptions.ExplicitCapture)]
    public static partial Regex CheckpointInfoPropertyNameRegex();
#else
    public static Regex CheckpointInfoPropertyNameRegex() => s_scopeKeyPropertyNameRegex;
    private static readonly Regex s_scopeKeyPropertyNameRegex =
        new(CheckpointInfoPropertyNamePattern, RegexOptions.Compiled | RegexOptions.CultureInvariant | RegexOptions.ExplicitCapture);
#endif

    protected override CheckpointInfo Parse(string propertyName)
    {
        Match scopeKeyPatternMatch = CheckpointInfoPropertyNameRegex().Match(propertyName);
        if (!scopeKeyPatternMatch.Success)
        {
            throw new JsonException($"Invalid CheckpointInfo property name format. Got '{propertyName}'.");
        }

        string runId = scopeKeyPatternMatch.Groups["runId"].Value;
        string checkpointId = scopeKeyPatternMatch.Groups["checkpointId"].Value;

        return new(Unescape(runId)!, Unescape(checkpointId)!);
    }

    protected override string Stringify([DisallowNull] CheckpointInfo value)
    {
        string? runIdEscaped = Escape(value.RunId);
        string? checkpointIdEscaped = Escape(value.CheckpointId);

        return $"{runIdEscaped}|{checkpointIdEscaped}";
    }
}
