// Copyright (c) Microsoft. All rights reserved.

namespace GettingStarted.TestRunner;

/// <summary>
/// Represents information about a configuration key.
/// </summary>
public class ConfigurationKeyInfo
{
    public string Key { get; set; } = string.Empty;
    public bool HasValue { get; set; }
    public bool IsRequired { get; set; }
    public bool IsSecret { get; set; }
    public string CurrentValue { get; set; } = string.Empty;
    public string FriendlyName { get; set; } = string.Empty;
}
