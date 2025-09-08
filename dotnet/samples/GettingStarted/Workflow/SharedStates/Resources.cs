// Copyright (c) Microsoft. All rights reserved.

using System.IO;

namespace WorkflowSharedStatesSample;

/// <summary>
/// Resource helper to load resources.
/// </summary>
internal static class Resources
{
    private const string ResourceFolder = "Resources";

    public static string Read(string fileName) => File.ReadAllText($"{ResourceFolder}/{fileName}");
}
