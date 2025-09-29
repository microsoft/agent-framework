// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows.Declarative.CodeGen;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

public class EdgeTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public void InitializeNext()
    {
        this.ExecuteTest("set_variable_1", "invoke_agent_2");
    }

    private void ExecuteTest(string sourceId, string targetId)
    {
        // Arrange
        EdgeTemplate template = new(sourceId, targetId);

        // Act
        string workflowCode = template.TransformText();
        this.Output.WriteLine(workflowCode.Trim());

        // Assert
        Assert.Equal("builder.AddEdge(setVariable1, invokeAgent2);", workflowCode.Trim());
    }
}
