// Copyright (c) Microsoft. All rights reserved.

namespace GettingStarted.TestRunner;

/// <summary>
/// Represents a test class.
/// </summary>
public class TestClass
{
    public string Name { get; set; } = string.Empty;
    public string FullName { get; set; } = string.Empty;
    public string Description { get; set; } = string.Empty;
    public Type Type { get; set; } = null!;
    public List<TestMethod> Methods { get; set; } = new();
}
