// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Agents.AI.TypeSafe;

/// <summary>
/// A tool's JSON schema cannot be expressed as Jev questions, so the tool is left out of the request.
/// </summary>
/// <remarks>
/// It is caught while a tool call plan is compiled and never leaves this package: an unsupported tool is logged and
/// excluded, or, when the tool mode requires a call and no tool remains, its reason becomes part of an
/// <see cref="InvalidOperationException"/>.
/// </remarks>
internal sealed class JevUnsupportedToolSchemaException : NotSupportedException
{
    public JevUnsupportedToolSchemaException()
    {
    }

    public JevUnsupportedToolSchemaException(string message)
        : base(message)
    {
    }

    public JevUnsupportedToolSchemaException(string message, Exception innerException)
        : base(message, innerException)
    {
    }
}
