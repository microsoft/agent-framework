// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.Workflows.Declarative.Extensions;
using Microsoft.Agents.Workflows.Declarative.Kit;
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

    protected void AssertGeneratedCode<TBase>(string actionId, string workflowCode) where TBase : class
    {
        Assert.Contains($"internal sealed class {actionId.FormatType()}", workflowCode);
        Assert.Contains($") : {typeof(TBase).Name}(", workflowCode);
        Assert.Contains(@$"""{actionId}""", workflowCode);
    }

    protected void AssertGeneratedMethod(string methodName, string workflowCode) =>
        Assert.Contains($"ValueTask {methodName}(", workflowCode);

    protected void AssertGeneratedAssignment(PropertyPath? variablePath, string workflowCode)
    {
        Assert.NotNull(variablePath);
        Assert.Contains(@$"key: ""{variablePath.VariableName}""", workflowCode);
        Assert.Contains(@$"scopeName: ""{variablePath.VariableScopeName}""", workflowCode);
    }

    protected void AssertDelegate(string actionId, string rootId, string workflowCode)
    {
        Assert.Contains($"{nameof(DelegateExecutor)} {actionId.FormatName()} = new(", workflowCode);
        Assert.Contains(@$"""{actionId}""", workflowCode);
        Assert.Contains($"{rootId.FormatName()}.Session", workflowCode);
    }
}
