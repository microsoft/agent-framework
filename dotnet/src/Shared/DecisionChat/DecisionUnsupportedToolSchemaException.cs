// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.Decisions;

/// <summary>
/// A tool's JSON schema cannot be expressed as closed-set decision questions, so the tool is left out of the request.
/// </summary>
/// <remarks>
/// It is caught while a tool call plan is compiled and never leaves the compiler: an unsupported tool is logged and
/// excluded, or, when the tool mode requires a call and no tool remains, its reason becomes part of an
/// <see cref="InvalidOperationException"/>.
/// </remarks>
internal sealed class DecisionUnsupportedToolSchemaException : NotSupportedException
{
    public DecisionUnsupportedToolSchemaException()
    {
    }

    public DecisionUnsupportedToolSchemaException(string message)
        : base(message)
    {
    }

    public DecisionUnsupportedToolSchemaException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}
