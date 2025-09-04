// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Declarative.Templates;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.Templates;

public class EdgeTemplateTest(ITestOutputHelper output) : WorkflowActionTemplateTest(output)
{
    [Fact]
    public async Task InitializeRoot()
    {
        await this.ExecuteTest("set_variable_1");
    }

    [Fact]
    public async Task InitializeNext()
    {
        await this.ExecuteTest("invoke_agent_2", "set_variable_1");
    }

    private async Task ExecuteTest(string targetId, string? sourceId = null)
    {
        // Arrange
        EdgeTemplate template = new(targetId, sourceId);

        // Act
        string text = this.Execute(() => template.TransformText());

        // Assert
        this.Output.WriteLine(text); // %%% TODO: VALIDATE
    }
}
