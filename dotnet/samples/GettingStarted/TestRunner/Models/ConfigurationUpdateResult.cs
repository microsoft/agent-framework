// Copyright (c) Microsoft. All rights reserved.

namespace GettingStarted.TestRunner;

/// <summary>
/// Represents the result of configuration update operations.
/// </summary>
public class ConfigurationUpdateResult
{
    public bool Success { get; set; }
    public List<string> FailedKeys { get; set; } = new();
}
