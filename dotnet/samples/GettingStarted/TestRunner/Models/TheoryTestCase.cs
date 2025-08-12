// Copyright (c) Microsoft. All rights reserved.

namespace GettingStarted.TestRunner;

/// <summary>
/// Represents a theory test case.
/// </summary>
public class TheoryTestCase
{
    public string DisplayName { get; set; } = string.Empty;
    public List<TheoryParameter> Parameters { get; set; } = new();
}
