// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.LocalCodeAct;

/// <summary>
/// Exception thrown when AST validation of generated Python code fails.
/// </summary>
public sealed class CodeValidationException : Exception
{
    /// <summary>Initializes a new instance of the <see cref="CodeValidationException"/> class.</summary>
    public CodeValidationException()
    {
    }

    /// <summary>Initializes a new instance of the <see cref="CodeValidationException"/> class.</summary>
    /// <param name="message">Validation error message.</param>
    public CodeValidationException(string message) : base(message)
    {
    }

    /// <summary>Initializes a new instance of the <see cref="CodeValidationException"/> class.</summary>
    /// <param name="message">Validation error message.</param>
    /// <param name="innerException">Underlying exception.</param>
    public CodeValidationException(string message, Exception innerException) : base(message, innerException)
    {
    }
}
