// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.LocalCodeAct.Internal;

/// <summary>Validates an explicit interpreter file path without current-directory or PATH lookup.</summary>
internal static class PythonExecutablePath
{
    public static void Validate(string pythonExecutablePath)
    {
        _ = Throw.IfNullOrWhitespace(pythonExecutablePath);

        if (!Path.IsPathFullyQualified(pythonExecutablePath))
        {
            throw new ArgumentException(
                "The Python executable path must be fully qualified.",
                nameof(pythonExecutablePath));
        }

        if (!File.Exists(pythonExecutablePath))
        {
            throw new FileNotFoundException("The Python executable file was not found.", pythonExecutablePath);
        }
    }
}
