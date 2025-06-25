// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Shared.Samples;

/// <summary>
/// Resource helper to load resources.
/// </summary>
internal static class Resources
{
    private const string ResourceFolder = "Resources";

    internal static string Read(string fileName) => File.ReadAllText($"{ResourceFolder}/{fileName}");

    internal static Task<string> ReadAsync(string fileName) => File.ReadAllTextAsync($"{ResourceFolder}/{fileName}");
}
