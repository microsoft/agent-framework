// Copyright (c) Microsoft. All rights reserved.

namespace GettingStarted.TestRunner;

/// <summary>
/// Represents a test folder/namespace.
/// </summary>
public class TestFolder
{
    public string Name { get; set; } = string.Empty;
    public List<TestClass> Classes { get; set; } = new();
}
