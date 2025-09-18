// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Reflection;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.Interpreter;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowModel"/>.
/// </summary>
public sealed class DeclarativeWorkflowModelTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Fact]
    public void GetDepthForDefault()
    {
        DeclarativeWorkflowModel model = new(CreateExecutor("root"));
        Assert.Equal(0, model.GetDepth(null));
    }

    [Fact]
    public void GetDepthForMissingNode()
    {
        DeclarativeWorkflowModel model = new(CreateExecutor("root"));
        Assert.Throws<DeclarativeModelException>(() => model.GetDepth("missing"));
    }

    [Fact]
    public void ConnectMissingNode()
    {
        TestExecutor rootExecutor = CreateExecutor("root");
        DeclarativeWorkflowModel model = new(rootExecutor);
        model.AddLink("root", "missing");
        WorkflowBuilder workflowBuilder = new(rootExecutor);
        Assert.Throws<DeclarativeModelException>(() => model.ConnectNodes(workflowBuilder));
    }

    [Fact]
    public void AddToMissingParent()
    {
        DeclarativeWorkflowModel model = new(CreateExecutor("root"));
        Assert.Throws<DeclarativeModelException>(() => model.AddNode(CreateExecutor("next"), "missing"));
    }

    [Fact]
    public void LinkFromMissingSource()
    {
        DeclarativeWorkflowModel model = new(CreateExecutor("root"));
        Assert.Throws<DeclarativeModelException>(() => model.AddLink("missing", "anything"));
    }

    [Fact]
    public void LocateMissingParent()
    {
        DeclarativeWorkflowModel model = new(CreateExecutor("root"));
        Assert.Null(model.LocateParent<TestExecutor>(null));
        Assert.Throws<DeclarativeModelException>(() => model.LocateParent<TestExecutor>("missing"));
    }

    private static TestExecutor CreateExecutor(string id) => new(id);

    internal sealed class TestExecutor(string actionId) :
        ReflectingExecutor<TestExecutor>(actionId),
        IMessageHandler<string>
    {
        public async ValueTask HandleAsync(string message, IWorkflowContext context) =>
            await context.SendMessageAsync($"{this.Id}: {DateTime.UtcNow:t}").ConfigureAwait(false);
    }
}
