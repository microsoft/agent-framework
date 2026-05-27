// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;

namespace Microsoft.Agents.AI.Compaction;

/// <summary>
/// Provides shared telemetry infrastructure for compaction operations.
/// </summary>
internal static class CompactionTelemetry
{
    /// <summary>
    /// The <see cref="ActivitySource"/> used to create activities for compaction operations.
    /// </summary>
    public static readonly ActivitySource ActivitySource = new(OpenTelemetryConsts.DefaultSourceName);

    /// <summary>
    /// Activity names used by compaction tracing.
    /// </summary>
    public static class ActivityNames
    {
        public const string Compact = "compaction.compact";
        public const string CompactionProviderInvoke = "compaction.provider.invoke";
        public const string Summarize = "compaction.summarize";
    }

    /// <summary>
    /// Tag names used on compaction activities.
    /// </summary>
    public static class Tags
    {
        public const string Strategy = "compaction.strategy";
        public const string Triggered = "compaction.triggered";
        public const string Compacted = "compaction.compacted";
        public const string BeforeTokens = "compaction.before.tokens";
        public const string AfterTokens = "compaction.after.tokens";
        public const string BeforeMessages = "compaction.before.messages";
        public const string AfterMessages = "compaction.after.messages";
        public const string BeforeGroups = "compaction.before.groups";
        public const string AfterGroups = "compaction.after.groups";
        public const string DurationMs = "compaction.duration_ms";
        public const string GroupsSummarized = "compaction.groups_summarized";
        public const string SummaryLength = "compaction.summary_length";
    }
}
