// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class ProviderTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public async Task WithNamespaceAsync()
    {
        await this.ExecuteTestAsync(
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
    public async Task WithoutNamespaceAsync()
    {
        await this.ExecuteTestAsync(
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

    private async Task ExecuteTestAsync(
        string[] executors,
        string[] instances,
        string[] edges,
        string? workflowNamespace = null)
    {
        // Arrange
        ProviderTemplate template = new("worflow-id", executors, instances, edges) { Namespace = workflowNamespace };

        // Act
        string workflowCode = template.TransformText();

        // Assert
        this.Output.WriteLine(workflowCode);

        Assert.True(Contains(executors));
        Assert.True(Contains(instances));
        Assert.True(Contains(edges));

        bool Contains(string[] code)
        {
            foreach (string block in code)
            {
                foreach (string line in block.Split('\n'))
                {
                    if (!workflowCode.Contains(line.Trim()))
                    {
                        return false;
                    }
                }
            }

            return true;
        }
    }
}
