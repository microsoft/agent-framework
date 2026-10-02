// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Postgres;

/// <summary>
/// Builds model prompts for PostgreSQL memory processing.
/// </summary>
internal static class PostgresMemoryPrompts
{
    public static List<ChatMessage> BuildExtractMemoriesMessages(
        string systemPrompt,
        IReadOnlyList<PostgresMemoryRecord> turns,
        IReadOnlyList<PostgresMemoryRecord> existingMemories)
    {
        var turnsText = string.Join(Environment.NewLine, turns.Select(t => $"{t.Role}: {t.Content}"));
        var existingText = existingMemories.Count == 0
            ? "(none)"
            : string.Join(
                Environment.NewLine,
                existingMemories.Select(m => $"[{PostgresMemoryStore.ToStoreValue(m.MemoryType)}] {m.Content}"));

        return
        [
            new ChatMessage(ChatRole.System, systemPrompt),
            new ChatMessage(
                ChatRole.User,
                $"""
                Conversation excerpt:
                {turnsText}

                Existing active memories (avoid duplicating these):
                {existingText}
                """),
        ];
    }

    public static List<ChatMessage> BuildThreadSummaryMessages(
        string systemPrompt,
        string? previousSummary,
        IReadOnlyList<PostgresMemoryRecord> turns)
    {
        var turnsText = string.Join(Environment.NewLine, turns.Select(t => $"{t.Role}: {t.Content}"));
        return
        [
            new ChatMessage(ChatRole.System, systemPrompt),
            new ChatMessage(
                ChatRole.User,
                $"""
                Previous summary:
                {(string.IsNullOrWhiteSpace(previousSummary) ? "(none)" : previousSummary)}

                New turns:
                {turnsText}
                """),
        ];
    }

    public static List<ChatMessage> BuildUserSummaryMessages(
        string systemPrompt,
        string? previousSummary,
        IReadOnlyList<PostgresMemoryRecord> memories,
        IReadOnlyList<PostgresMemoryRecord> threadSummaries)
    {
        var memoriesText = memories.Count == 0
            ? "(none)"
            : string.Join(
                Environment.NewLine,
                memories.Select(m =>
                    $"[{PostgresMemoryStore.ToStoreValue(m.MemoryType)} confidence={m.Confidence:0.00}] {m.Content}"));
        var summariesText = threadSummaries.Count == 0
            ? "(none)"
            : string.Join(Environment.NewLine, threadSummaries.Select(s => s.Content));

        return
        [
            new ChatMessage(ChatRole.System, systemPrompt),
            new ChatMessage(
                ChatRole.User,
                $"""
                Previous user summary:
                {(string.IsNullOrWhiteSpace(previousSummary) ? "(none)" : previousSummary)}

                Active memories:
                {memoriesText}

                Latest thread summaries:
                {summariesText}
                """),
        ];
    }

    public static List<ChatMessage> BuildReconcileMessages(
        string systemPrompt,
        IReadOnlyList<PostgresMemoryRecord> memories)
    {
        var memoriesText = string.Join(
            Environment.NewLine,
            memories.Select(m =>
                $"{m.Id}: [{PostgresMemoryStore.ToStoreValue(m.MemoryType)} confidence={m.Confidence:0.00} created={m.CreatedAt:O}] {m.Content}"));

        return
        [
            new ChatMessage(ChatRole.System, systemPrompt),
            new ChatMessage(ChatRole.User, $"Active memories:\n{memoriesText}"),
        ];
    }
}
