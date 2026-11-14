// Copyright (c) Microsoft. All rights reserved.

using System;

namespace Microsoft.Shared.Diagnostics;

/// <summary>Validates values before they reach HTTP header transport APIs.</summary>
internal static class HttpHeaderValidation
{
    public static void ValidateNoProhibitedCharacters(string value, string parameterName, string message)
    {
        if (value.IndexOfAny(['\r', '\n', '\0']) >= 0)
        {
            throw new ArgumentException(message, parameterName);
        }
    }
}
