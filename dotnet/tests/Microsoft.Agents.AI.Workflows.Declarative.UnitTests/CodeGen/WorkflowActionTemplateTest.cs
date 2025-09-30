// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Extensions;
using Microsoft.Agents.AI.Workflows.Declarative.Kit;
using Microsoft.Bot.ObjectModel;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

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

    protected static void AssertGeneratedCode<TBase>(string actionId, string workflowCode) where TBase : class
    {
        Assert.Contains($"internal sealed class {actionId.FormatType()}", workflowCode);
        Assert.Contains($") : {typeof(TBase).Name}(", workflowCode);
        Assert.Contains(@$"""{actionId}""", workflowCode);
    }

    protected static void AssertGeneratedMethod(string methodName, string workflowCode) =>
        Assert.Contains($"ValueTask {methodName}(", workflowCode);

    protected static void AssertAgentProvider(bool expected, string workflowCode)
    {
        if (expected)
        {
            Assert.Contains(", WorkflowAgentProvider agentProvider", workflowCode);
        }
        else
        {
            Assert.DoesNotContain(", WorkflowAgentProvider agentProvider", workflowCode);
        }
    }

    protected static void AssertOptionalAssignment(PropertyPath? variablePath, string workflowCode)
    {
        if (variablePath is not null)
        {
            Assert.Contains(@$"key: ""{variablePath.VariableName}""", workflowCode);
            Assert.Contains(@$"scopeName: ""{variablePath.NamespaceAlias}""", workflowCode);
        }
    }

    protected static void AssertGeneratedAssignment(PropertyPath? variablePath, string workflowCode)
    {
        Assert.NotNull(variablePath);
        Assert.Contains(@$"key: ""{variablePath.VariableName}""", workflowCode);
        Assert.Contains(@$"scopeName: ""{variablePath.NamespaceAlias}""", workflowCode);
    }

    protected static void AssertDelegate(string actionId, string rootId, string workflowCode)
    {
        Assert.Contains($"{nameof(DelegateExecutor)} {actionId.FormatName()} = new(", workflowCode);
        Assert.Contains(@$"""{actionId}""", workflowCode);
        Assert.Contains($"{rootId.FormatName()}.Session", workflowCode);
    }
}
