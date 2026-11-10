// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using Microsoft.Shared.Diagnostics;

namespace Microsoft.Agents.AI.LocalCodeAct.Internal;

/// <summary>Validates the interpreter path before extracting scripts or starting child processes.</summary>
internal static class PythonExecutablePath
{
    public static void Validate(string pythonExecutablePath)
    {
        _ = Throw.IfNullOrWhitespace(pythonExecutablePath);

        if (OperatingSystem.IsWindows())
        {
            if (!Path.IsPathFullyQualified(pythonExecutablePath))
            {
                throw new ArgumentException(
                    "On Windows, the Python executable path must be fully qualified.",
                    nameof(pythonExecutablePath));
            }

            if (!File.Exists(pythonExecutablePath))
            {
                throw new FileNotFoundException("The Python executable file was not found.", pythonExecutablePath);
            }
        }
    }
}
