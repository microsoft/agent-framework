// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Threading.Tasks;
using Shared.Code;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
public sealed class DeclarativeEjectionTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Theory]
    [InlineData("AddConversationMessage.yaml")]
    [InlineData("CancelWorkflow.yaml")]
    [InlineData("ClearAllVariables.yaml")]
    [InlineData("CopyConversationMessages.yaml")]
    [InlineData("Condition.yaml")]
    [InlineData("ConditionElse.yaml")]
    [InlineData("CreateConversation.yaml")]
    [InlineData("EditTable.yaml")]
    [InlineData("EditTableV2.yaml")]
    [InlineData("EndConversation.yaml")]
    [InlineData("EndWorkflow.yaml")]
    [InlineData("Goto.yaml")]
    [InlineData("InvokeAgent.yaml")]
    [InlineData("LoopBreak.yaml")]
    [InlineData("LoopContinue.yaml")]
    [InlineData("LoopEach.yaml")]
    [InlineData("ParseValue.yaml")]
    [InlineData("ResetVariable.yaml")]
    [InlineData("RetrieveConversationMessage.yaml")]
    [InlineData("RetrieveConversationMessages.yaml")]
    [InlineData("SendActivity.yaml")]
    [InlineData("SetVariable.yaml")]
    [InlineData("SetTextVariable.yaml")]
    public Task ExecuteActionAsync(string workflowFile) =>
        this.EjectWorkflowAsync(workflowFile);

    private async Task EjectWorkflowAsync(string workflowFile)
    {
        using StreamReader yamlReader = File.OpenText(Path.Combine("Workflows", workflowFile));
        string workflowCode = DeclarativeWorkflowBuilder.Eject(yamlReader, DeclarativeWorkflowLanguage.CSharp, "Test.WorkflowProviders");

        string baselinePath = Path.Combine("Workflows", Path.ChangeExtension(workflowFile, ".cs"));
        string generatedPath = Path.Combine("Workflows", Path.ChangeExtension(workflowFile, ".g.cs"));

        this.Output.WriteLine($"WRITING BASELINE TO: {Path.GetFullPath(generatedPath)}\n");

        try
        {
            File.WriteAllText(Path.GetFullPath(generatedPath), workflowCode);
            Compiler.Build(workflowCode, Compiler.RepoDependencies(typeof(DeclarativeWorkflowBuilder))); // Throws if build fails
        }
        finally
        {
            Console.WriteLine(workflowCode);
        }

        string expectedCode = File.ReadAllText(baselinePath);
        string[] expectedLines = expectedCode.Trim().Split('\n');
        string[] workflowLines = workflowCode.Trim().Split('\n');

        Assert.Equal(expectedLines.Length, workflowLines.Length);

        for (int index = 0; index < workflowLines.Length; ++index)
        {
            this.Output.WriteLine($"Comparing line #{index + 1}/{workflowLines.Length}.");
            Assert.Equal(expectedLines[index].Trim(), workflowLines[index].Trim());
        }
    }
}
