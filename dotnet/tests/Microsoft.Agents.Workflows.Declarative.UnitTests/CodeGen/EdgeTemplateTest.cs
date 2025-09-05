// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.CodeGen;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

public class EdgeTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public async Task InitializeNext()
    {
        await this.ExecuteTest("set_variable_1", "invoke_agent_2");
    }

    private async Task ExecuteTest(string targetId, string sourceId)
    {
        // Arrange
        EdgeTemplate template = new(sourceId, targetId);

        // Act
        string text = this.Execute(() => template.TransformText());

        // Assert
        this.Output.WriteLine(text); // %%% TODO: VALIDATE
    }
}
