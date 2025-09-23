// Copyright (c) Microsoft. All rights reserved.

#define CREATE_BASELINE // %%% DISABLE

using System;
using System.IO;
using System.Threading.Tasks;
using Xunit.Abstractions;

namespace Microsoft.Agents.Workflows.Declarative.UnitTests.CodeGen;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
public sealed class DeclarativeEjectionTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Theory]
    [InlineData("ClearAllVariables.yaml")]
    [InlineData("EditTable.yaml")]
    [InlineData("EditTableV2.yaml")]
    [InlineData("Goto.yaml")]
    [InlineData("LoopBreak.yaml")]
    [InlineData("LoopContinue.yaml")]
    [InlineData("LoopEach.yaml")]
    [InlineData("ParseValue.yaml")]
    [InlineData("ResetVariable.yaml")]
    [InlineData("SendActivity.yaml")]
    [InlineData("SetVariable.yaml")]
    [InlineData("SetTextVariable.yaml")]
    public Task ExecuteActionAsync(string workflowFile) =>
        this.EjectWorkflowAsync(workflowFile);

    private async Task EjectWorkflowAsync(string workflowPath)
    {
        using StreamReader yamlReader = File.OpenText(Path.Combine("Workflows", workflowPath));
        string workflowCode = DeclarativeWorkflowBuilder.Eject(yamlReader, DeclarativeWorkflowLanguage.CSharp, "Test.Workflow");

        string baselinePath = Path.Combine("Workflows", Path.ChangeExtension(workflowPath, ".cs"));
#if CREATE_BASELINE
        this.Output.WriteLine($"WRITING BASELINE TO: {Path.GetFullPath(baselinePath)}\n");
#else
        string expectedCode = File.ReadAllText(baselinePath);
#endif

        Console.WriteLine(workflowCode);

#if CREATE_BASELINE
        File.WriteAllText(Path.GetFullPath(baselinePath), workflowCode);
#else
        string[] expectedLines = expectedCode.Trim().Split('\n');
        string[] workflowLines = workflowCode.Trim().Split('\n');

        Assert.Equal(expectedLines.Length, workflowLines.Length);

        for (int index = 0; index < workflowLines.Length; ++index)
        {
            this.Output.WriteLine($"Comparing line #{index + 1}/{workflowLines.Length}.");
            Assert.Equal(expectedLines[index].Trim(), workflowLines[index].Trim());
        }
#endif
    }
}
