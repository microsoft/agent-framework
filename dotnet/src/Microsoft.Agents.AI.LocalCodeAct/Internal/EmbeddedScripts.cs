// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;

namespace Microsoft.Agents.AI.LocalCodeAct.Internal;

/// <summary>
/// Extracts the embedded Python <c>runner.py</c> and <c>validator.py</c> scripts to a temporary
/// directory and caches their paths for the lifetime of the process.
/// </summary>
internal static class EmbeddedScripts
{
    private static readonly object s_syncRoot = new();
    private static string? s_runnerPath;
    private static string? s_validatorPath;

    /// <summary>Returns the path to the embedded <c>runner.py</c>, extracting it on first access.</summary>
    public static string GetRunnerScriptPath() => GetOrExtract("runner.py", ref s_runnerPath);

    /// <summary>Returns the path to the embedded <c>validator.py</c>, extracting it on first access.</summary>
    public static string GetValidatorScriptPath() => GetOrExtract("validator.py", ref s_validatorPath);

    private static string GetOrExtract(string fileName, ref string? cached)
    {
        if (cached is not null && File.Exists(cached))
        {
            return cached;
        }

        lock (s_syncRoot)
        {
            if (cached is not null && File.Exists(cached))
            {
                return cached;
            }

            var path = Extract(fileName);
            if (fileName == "runner.py")
            {
                s_runnerPath = path;
            }
            else
            {
                s_validatorPath = path;
            }

            cached = path;
            return path;
        }
    }

    private static string Extract(string fileName)
    {
        var assembly = typeof(EmbeddedScripts).Assembly;
        var resourceName = $"Microsoft.Agents.AI.LocalCodeAct.Resources.{fileName}";

        using var stream = assembly.GetManifestResourceStream(resourceName)
            ?? throw new InvalidOperationException($"Embedded resource '{resourceName}' not found.");

        var dir = Path.Combine(Path.GetTempPath(), "agentframework-localcodeact-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        var path = Path.Combine(dir, fileName);

        using var fileStream = File.Create(path);
        stream.CopyTo(fileStream);
        return path;
    }
}
