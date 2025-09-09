// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

/// <summary>
/// Base test class for text template.
/// </summary>
public abstract class WorkflowActionTemplateTest(ITestOutputHelper output) : WorkflowTest(output)
{
    private int ActionIndex { get; set; } = 1;

#pragma warning disable CA1308 // Normalize strings to uppercase
    protected ActionId CreateActionId(string seed) => new($"{seed.ToLowerInvariant()}_{this.ActionIndex++}");
#pragma warning restore CA1308 // Normalize strings to uppercase

    protected string FormatDisplayName(string name) => $"{this.GetType().Name}_{name}";
}
