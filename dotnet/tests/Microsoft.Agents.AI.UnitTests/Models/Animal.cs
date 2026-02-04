// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Agents.AI.UnitTests;

public sealed class Animal
{
    public int Id { get; set; }
    public string? FullName { get; set; }
    public Species Species { get; set; }
}

public enum Species
{
    Bear,
    Tiger,
    Walrus,
}
