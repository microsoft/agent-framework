// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Extensions.Compliance.Redaction;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI;

/// <summary>
/// A <see cref="Redactor"/> that replaces the entire input with a fixed replacement string.
/// </summary>
internal sealed class ReplacingRedactor : Redactor
{
    private readonly string _replacementText;

    /// <summary>
    /// Initializes a new instance of the <see cref="ReplacingRedactor"/> class.
    /// </summary>
    /// <param name="replacementText">The text to substitute for any input value.</param>
    /// <exception cref="ArgumentNullException">Thrown when <paramref name="replacementText"/> is <see langword="null"/>.</exception>
    public ReplacingRedactor(string replacementText)
    {
        this._replacementText = Throw.IfNull(replacementText);
    }

    /// <inheritdoc />
    public override int GetRedactedLength(ReadOnlySpan<char> input) => this._replacementText.Length;

    /// <inheritdoc />
    public override int Redact(ReadOnlySpan<char> source, Span<char> destination)
    {
        this._replacementText.AsSpan().CopyTo(destination);
        return this._replacementText.Length;
    }
}
