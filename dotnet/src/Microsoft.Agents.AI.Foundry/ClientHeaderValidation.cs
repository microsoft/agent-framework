// Copyright (c) Microsoft. All rights reserved.

using System;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.Foundry;

/// <summary>Validates client header names and values before they reach request transport APIs.</summary>
internal static class ClientHeaderValidation
{
    private const string ClientHeaderPrefix = "x-client-";

    public static void Validate(string name, string value)
    {
        _ = Throw.IfNull(name);
        _ = Throw.IfNull(value);

        if (string.IsNullOrWhiteSpace(name))
        {
            throw new ArgumentException("Header name must not be empty or whitespace.", nameof(name));
        }

        // Reject line breaks before using the name in exception text or a transport API.
        if (ContainsNewLine(name))
        {
            throw new ArgumentException("Header name must not contain carriage-return or line-feed characters.", nameof(name));
        }

        if (value.Length == 0)
        {
            throw new ArgumentException("Header value must not be empty.", nameof(value));
        }

        if (ContainsNewLine(value))
        {
            throw new ArgumentException("Header value must not contain carriage-return or line-feed characters.", nameof(value));
        }

        if (!name.StartsWith(ClientHeaderPrefix, StringComparison.OrdinalIgnoreCase))
        {
            throw new ArgumentException(
                $"Header name '{name}' must start with '{ClientHeaderPrefix}' (case-insensitive). Only x-client-* headers are forwarded by the Foundry platform.",
                nameof(name));
        }
    }

    private static bool ContainsNewLine(string value) =>
        value.IndexOf('\r') >= 0 || value.IndexOf('\n') >= 0;
}
