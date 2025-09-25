// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;

namespace Microsoft.Agents.AI.Abstractions.UnitTests.Models;

[Description("Some test description")]
internal sealed class Animal
{
    public int Id { get; set; }
    public string? FullName { get; set; }
    public Species Species { get; set; }
}
