// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.AzureAI.ContentUnderstanding;

/// <summary>
/// Phase 9 — outcome of an attempted vector-store upload for one document. Carries the updated
/// <see cref="DocumentEntry"/> (status/error/file-id/upload-duration stamps) and an optional
/// short note to splice into <c>AIContext.Messages</c>. <see cref="UpdatedEntry"/> may be
/// reference-equal to the input when no mutation is needed (skip path).
/// </summary>
internal readonly record struct FileSearchOutcome(DocumentEntry? UpdatedEntry, string? NoteText)
{
    public static FileSearchOutcome Success(DocumentEntry entry, string note) => new(entry, note);
    public static FileSearchOutcome Fail(DocumentEntry entry, string note) => new(entry, note);
    public static FileSearchOutcome Skip(DocumentEntry entry, string? note) => new(entry, note);
}
