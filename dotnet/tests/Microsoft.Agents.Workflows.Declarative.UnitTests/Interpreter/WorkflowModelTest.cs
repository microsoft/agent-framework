// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Interpreter;
using Microsoft.Agents.Workflows.Reflection;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.Interpreter;

/// <summary>
/// Tests execution of workflow created by <see cref="WorkflowModel"/>.
/// </summary>
public sealed class DeclarativeWorkflowModelTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Fact]
    public async Task GetDepthForDefault()
    {
        WorkflowModel model = new(this.CreateExecutor("root"));
        Assert.Equal(0, model.GetDepth(null));
    }

    [Fact]
    public async Task GetDepthForMissingNode()
    {
        WorkflowModel model = new(this.CreateExecutor("root"));
        Assert.Throws<UnknownActionException>(() => model.GetDepth("missing"));
    }

    [Fact]
    public async Task ConnectMissingNode()
    {
        TestExecutor rootExecutor = this.CreateExecutor("root");
        WorkflowModel model = new(rootExecutor);
        model.AddLink("root", "missing");
        WorkflowBuilder workflowBuilder = new(rootExecutor);
        Assert.Throws<WorkflowModelException>(() => model.ConnectNodes(workflowBuilder));
    }

    [Fact]
    public async Task AddToMissingParent()
    {
        WorkflowModel model = new(this.CreateExecutor("root"));
        Assert.Throws<UnknownActionException>(() => model.AddNode(this.CreateExecutor("next"), "missing"));
    }

    [Fact]
    public async Task LinkFromMissingSource()
    {
        WorkflowModel model = new(this.CreateExecutor("root"));
        Assert.Throws<UnknownActionException>(() => model.AddLink("missing", "anything"));
    }

    [Fact]
    public async Task LocateMissingParent()
    {
        WorkflowModel model = new(this.CreateExecutor("root"));
        Assert.Null(model.LocateParent<TestExecutor>(null));
        Assert.Throws<UnknownActionException>(() => model.LocateParent<TestExecutor>("missing"));
    }

    private TestExecutor CreateExecutor(string id) => new(id);

    internal sealed class TestExecutor(string actionId) :
        ReflectingExecutor<TestExecutor>(actionId),
        IMessageHandler<string>
    {
        public async ValueTask HandleAsync(string message, IWorkflowContext context)
        {
            await context.SendMessageAsync($"{this.Id}: {DateTime.UtcNow.ToShortTimeString()}").ConfigureAwait(false);
        }
    }
}
