// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Maps a resolved media type (plus an optional explicit override) to a Content Understanding
/// analyzer id.
/// </summary>
/// <remarks>
/// Auto-selection rules:
/// <c>audio/*</c> → <c>prebuilt-audioSearch</c>, <c>video/*</c> → <c>prebuilt-videoSearch</c>,
/// everything else → <c>prebuilt-documentSearch</c>. An explicit override always wins.
/// See <c>features/sdk/dotnet-cu-context-provider/dev-plan-dotnet-cu-context-provider.md</c>
/// "Phase 3".
/// </remarks>
internal static class AnalyzerSelector
{
    public const string AudioAnalyzer = "prebuilt-audioSearch";
    public const string VideoAnalyzer = "prebuilt-videoSearch";
    public const string DocumentAnalyzer = "prebuilt-documentSearch";

    public static string Select(string mediaType, string? explicitOverride)
    {
        if (!string.IsNullOrWhiteSpace(explicitOverride))
        {
            return explicitOverride!.Trim();
        }

        if (string.IsNullOrEmpty(mediaType))
        {
            return DocumentAnalyzer;
        }

        if (mediaType.StartsWith("audio/", StringComparison.OrdinalIgnoreCase))
        {
            return AudioAnalyzer;
        }

        if (mediaType.StartsWith("video/", StringComparison.OrdinalIgnoreCase))
        {
            return VideoAnalyzer;
        }

        return DocumentAnalyzer;
    }
}
