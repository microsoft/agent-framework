// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.Interpreter;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.Interpreter;

/// <summary>
/// Tests execution of workflow created by <see cref="WorkflowModel{TCondition}"/>.
/// </summary>
public sealed class DeclarativeWorkflowModelTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Fact]
    public void GetDepthForDefault()
    {
        WorkflowModel<string> model = new(new TestExecutor("root"));
        Assert.Equal(0, model.GetDepth(null));
    }

    [Fact]
    public void GetDepthForMissingNode()
    {
        WorkflowModel<string> model = new(new TestExecutor("root"));
        Assert.Throws<DeclarativeModelException>(() => model.GetDepth("missing"));
    }

    [Fact]
    public void ConnectMissingNode()
    {
        TestExecutor rootExecutor = new("root");
        WorkflowModel<string> model = new(rootExecutor);
        model.AddLink("root", "missing");
        TestWorkflowBuilder modelBuilder = new();
        Assert.Throws<DeclarativeModelException>(() => model.Build(modelBuilder));
    }

    [Fact]
    public void AddToMissingParent()
    {
        WorkflowModel<string> model = new(new TestExecutor("root"));
        Assert.Throws<DeclarativeModelException>(() => model.AddNode(new TestExecutor("next"), "missing"));
    }

    [Fact]
    public void LinkFromMissingSource()
    {
        WorkflowModel<string> model = new(new TestExecutor("root"));
        Assert.Throws<DeclarativeModelException>(() => model.AddLink("missing", "anything"));
    }

    [Fact]
    public void LocateMissingParent()
    {
        WorkflowModel<string> model = new(new TestExecutor("root"));
        Assert.Null(model.LocateParent<TestExecutor>(null));
        Assert.Throws<DeclarativeModelException>(() => model.LocateParent<TestExecutor>("missing"));
    }

    internal sealed class TestExecutor(string actionId) : IModeledAction
    {
        public string Id { get; } = actionId;
    }

    internal sealed class TestWorkflowBuilder : IModelBuilder<string>
    {
        public void Connect(IModeledAction source, IModeledAction target, string? condition = null)
        {
            Assert.Fail(); // Not expected to be called in this test.
        }
    }
}
