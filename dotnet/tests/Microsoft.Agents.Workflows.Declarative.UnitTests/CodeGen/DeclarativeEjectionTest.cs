// Copyright (c) Microsoft. All rights reserved.

using System.IO;
using System.Threading.Tasks;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
public sealed class DeclarativeEjectionTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Fact]
    public async Task GotoAction()
    {
        await this.EjectWorkflow("Goto.yaml");
    }

    [Theory]
    [InlineData("Single.yaml")]
    [InlineData("EditTable.yaml")]
    [InlineData("EditTableV2.yaml")]
    [InlineData("ParseValue.yaml")]
    [InlineData("SendActivity.yaml")]
    [InlineData("SetVariable.yaml")]
    [InlineData("SetTextVariable.yaml")]
    [InlineData("ClearAllVariables.yaml")]
    [InlineData("ResetVariable.yaml")]
    public async Task ExecuteAction(string workflowFile)
    {
        await this.EjectWorkflow(workflowFile);
    }

    private async Task EjectWorkflow(string workflowPath)
    {
        using StreamReader yamlReader = File.OpenText(Path.Combine("Workflows", workflowPath));

        string workflowCode = DeclarativeWorkflowBuilder.Eject(yamlReader, "Test.Workflow");

        this.Output.WriteLine(workflowCode); // %%% TODO: VALIDATE
    }
}
