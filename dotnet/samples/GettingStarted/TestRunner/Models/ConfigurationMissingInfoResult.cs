// Copyright (c) Microsoft. All rights reserved.

namespace GettingStarted.TestRunner;

/// <summary>
/// Represents information about a missing configuration key.
/// </summary>
public class ConfigurationMissingInfoResult
{
    public string Key { get; set; } = string.Empty;
    public string FriendlyName { get; set; } = string.Empty;
    public string DetailedDescription { get; set; } = string.Empty;
    public bool IsRequired { get; set; }
    public bool IsSecret { get; set; }
}
