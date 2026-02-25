// Copyright (c) Microsoft. All rights reserved.

using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.Text;

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// Represents location information in a form that supports value equality making it friendly for source gen caching.
/// </summary>
internal sealed record DiagnosticLocationInfo(
    string FilePath,
    TextSpan Span,
    LinePositionSpan LineSpan)
{
    /// <summary>
    /// Creates a DiagnosticLocationInfo from a Roslyn Location.
    /// </summary>
    public static DiagnosticLocationInfo? FromLocation(Location? location)
    {
        if (location is null || location == Location.None)
        {
            return null;
        }

        FileLinePositionSpan lineSpan = location.GetLineSpan();
        return new DiagnosticLocationInfo(
            lineSpan.Path ?? string.Empty,
            location.SourceSpan,
            lineSpan.Span);
    }

    /// <summary>
    /// Converts back to a Roslyn Location.
    /// </summary>
    public Location ToRoslynLocation()
    {
        if (string.IsNullOrWhiteSpace(this.FilePath))
        {
            return Location.None;
        }

        return Location.Create(this.FilePath, this.Span, this.LineSpan);
    }
}
