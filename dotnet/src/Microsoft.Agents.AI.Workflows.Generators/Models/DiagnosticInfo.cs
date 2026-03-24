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
    ImmutableEquatableArray<string> MessageArgs)
{
    /// <summary>
    /// Creates a DiagnosticInfo from a location and message arguments.
    /// </summary>
    public static DiagnosticInfo Create(string diagnosticId, Location location, params string[] messageArgs)
    {
        FileLinePositionSpan lineSpan = location.GetLineSpan();
        return new DiagnosticInfo(
            diagnosticId,
            lineSpan.Path ?? string.Empty,
            location.SourceSpan,
            lineSpan.Span,
            new ImmutableEquatableArray<string>(System.Collections.Immutable.ImmutableArray.Create(messageArgs)));
    }

    /// <summary>
    /// Converts this info back to a Roslyn Diagnostic.
    /// </summary>
    public Diagnostic ToRoslynDiagnostic(SyntaxTree? syntaxTree)
    {
        DiagnosticDescriptor? descriptor = DiagnosticDescriptors.GetById(this.DiagnosticId);
        if (descriptor is null)
        {
            // Fallback - should not happen
            object[] fallbackArgs = new object[this.MessageArgs.Count];
            for (int i = 0; i < this.MessageArgs.Count; i++)
            {
                fallbackArgs[i] = this.MessageArgs[i];
            }

            return Diagnostic.Create(
                DiagnosticDescriptors.InsufficientParameters,
                Location.None,
                fallbackArgs);
        }

        Location location;
        if (syntaxTree is not null)
        {
            location = Location.Create(syntaxTree, this.Span);
        }
        else if (!string.IsNullOrWhiteSpace(this.FilePath))
        {
            location = Location.Create(this.FilePath, this.Span, this.LineSpan);
        }
        else
        {
            location = Location.None;
        }

        object[] args = new object[this.MessageArgs.Count];
        for (int i = 0; i < this.MessageArgs.Count; i++)
        {
            args[i] = this.MessageArgs[i];
        }

        return Diagnostic.Create(descriptor, location, args);
    }
}
