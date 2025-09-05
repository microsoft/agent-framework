// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class ProviderTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public async Task WithNamespace()
    {
        await this.ExecuteTest(
            [
                """
                internal sealed class TestExecutor1() : ActionExecutor(id: "test_1")
                {
                    protected override ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
                    {
                       // Nothing to do
                       return default;
                    }
                }
                """
            ],
            [
                """
                TestExecutor1 test1 = new();
                """
            ],
            [
                """
                builder.AddEdge(builder.Root, test1);
                """
            ],
            "Test.Workflows.Generated");
    }

    [Fact]
    public async Task WithoutNamespace()
    {
        await this.ExecuteTest(
            [
                """
                internal sealed class TestExecutor1() : ActionExecutor(id: "test_1")
                {
                    protected override ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
                    {
                       // Nothing to do
                       return default;
                    }
                }

                internal sealed class TestExecutor2() : ActionExecutor(id: "test_2")
                {
                    protected override ValueTask ExecuteAsync(IWorkflowContext context, CancellationToken cancellationToken)
                    {
                       // Nothing to do
                       return default;
                    }
                }
                """
            ],
            [
                """
                TestExecutor1 test1 = new();
                TestExecutor2 test2 = new();
                """
            ],
            [
                """
                builder.AddEdge(builder.Root, test1);
                builder.AddEdge(test1, test2);
                """
            ]);
    }

    private async Task ExecuteTest(
        string[] executors,
        string[] instances,
        string[] edges,
        string? @namespace = null)
    {
        // Arrange
        ProviderTemplate template = new("worflow-id", executors, instances, edges) { Namespace = @namespace };

        // Act
        string text = this.Execute(() => template.TransformText());

        // Assert
        this.Output.WriteLine(text); // %%% TODO: VALIDATE
    }
}
