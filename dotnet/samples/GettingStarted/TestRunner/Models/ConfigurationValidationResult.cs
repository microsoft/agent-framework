// Copyright (c) Microsoft. All rights reserved.

namespace GettingStarted.TestRunner;

/// <summary>
/// Represents the result of configuration validation.
/// </summary>
public class ConfigurationValidationResult
{
    public bool IsValid { get; set; }
    public List<string> MissingKeys { get; set; } = new();
    public List<ConfigurationMissingInfoResult> MissingConfigurations { get; set; } = new();
}
