// Copyright (c) Microsoft. All rights reserved.

namespace GettingStarted.TestRunner;

/// <summary>
/// Represents a theory parameter.
/// </summary>
public class TheoryParameter
{
    public string Name { get; set; } = string.Empty;
    public Type Type { get; set; } = null!;
    public object? Value { get; set; }
}
