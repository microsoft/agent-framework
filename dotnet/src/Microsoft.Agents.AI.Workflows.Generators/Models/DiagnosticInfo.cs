// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Generators.Diagnostics;
using Microsoft.CodeAnalysis;
using Microsoft.CodeAnalysis.Text;

namespace Microsoft.Agents.AI.Workflows.Generators.Models;

/// <summary>
/// Represents diagnostic information in a form that supports value equality.
/// Location is stored as file path + span, which can be used to recreate a Location.
/// </summary>
internal sealed record DiagnosticInfo(
    string DiagnosticId,
    string FilePath,
    TextSpan Span,
    LinePositionSpan LineSpan,
    EquatableArray<string> MessageArgs)
{
    /// <summary>
    /// Creates a DiagnosticInfo from a location and message arguments.
    /// </summary>
    public static DiagnosticInfo Create(string diagnosticId, Location location, params string[] messageArgs)
    {
        var lineSpan = location.GetLineSpan();
        return new DiagnosticInfo(
            diagnosticId,
            lineSpan.Path ?? string.Empty,
            location.SourceSpan,
            lineSpan.Span,
            new EquatableArray<string>(System.Collections.Immutable.ImmutableArray.Create(messageArgs)));
    }

    /// <summary>
    /// Converts this info back to a Diagnostic.
    /// </summary>
    public Diagnostic ToDiagnostic(SyntaxTree? syntaxTree)
    {
        var descriptor = DiagnosticDescriptors.GetById(DiagnosticId);
        if (descriptor is null)
        {
            // Fallback - should not happen
            var fallbackArgs = new object[MessageArgs.Length];
            for (int i = 0; i < MessageArgs.Length; i++)
            {
                fallbackArgs[i] = MessageArgs[i];
            }

            return Diagnostic.Create(
                DiagnosticDescriptors.InsufficientParameters,
                Location.None,
                fallbackArgs);
        }

        Location location;
        if (syntaxTree is not null)
        {
            location = Location.Create(syntaxTree, Span);
        }
        else if (!string.IsNullOrEmpty(FilePath))
        {
            location = Location.Create(FilePath, Span, LineSpan);
        }
        else
        {
            location = Location.None;
        }

        var args = new object[MessageArgs.Length];
        for (int i = 0; i < MessageArgs.Length; i++)
        {
            args[i] = MessageArgs[i];
        }

        return Diagnostic.Create(descriptor, location, args);
    }
}
