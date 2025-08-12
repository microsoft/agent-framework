// Copyright (c) Microsoft. All rights reserved.

using System.Reflection;

namespace GettingStarted.TestRunner;

/// <summary>
/// Represents a test method.
/// </summary>
public class TestMethod
{
    public string Name { get; set; } = string.Empty;
    public MethodInfo MethodInfo { get; set; } = null!;
    public bool IsTheory { get; set; }
    public List<TheoryTestCase> TheoryData { get; set; } = new();
}
