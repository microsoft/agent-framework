// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Diagnostics;
using System.IO;
using System.Threading.Tasks;
using Xunit.Abstractions;

namespace Microsoft.Agents.AI.Workflows.Declarative.UnitTests.CodeGen;

/// <summary>
/// Tests execution of workflow created by <see cref="DeclarativeWorkflowBuilder"/>.
/// </summary>
public sealed class DeclarativeEjectionTest(ITestOutputHelper output) : WorkflowTest(output)
{
    [Theory]
    [InlineData("ClearAllVariables.yaml")]
    [InlineData("Condition.yaml")]
    [InlineData("ConditionElse.yaml")]
    [InlineData("EditTable.yaml")]
    [InlineData("EditTableV2.yaml")]
    [InlineData("EndConversation.yaml")]
    [InlineData("EndDialog.yaml")]
    [InlineData("Goto.yaml")]
    [InlineData("InvokeAgent.yaml")]
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
            this.BuildWorkflow(generatedPath);
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

    private void BuildWorkflow(string workflowPath)
    {
        string projectPath = Path.Combine("Projects", Path.GetFileNameWithoutExtension(workflowPath) + $"{DateTime.UtcNow:YYMMdd-HHmmss-fff}");
        string referencePath = Path.Combine(GetRepoFolder(), "dotnet/src/Microsoft.Agents.AI.Workflows.Declarative/Microsoft.Agents.AI.Workflows.Declarative.csproj");
        DirectoryInfo projectDirectory = Directory.CreateDirectory(Path.GetFullPath(projectPath));
        File.Copy(Path.GetFullPath(workflowPath), Path.Combine(projectDirectory.FullName, "Workflow.cs"));
        string projectText = File.ReadAllText(Path.GetFullPath("Workflows/TestProject.csproj"));
        File.WriteAllText(Path.Combine(projectDirectory.FullName, "TestProject.csproj"), projectText.Replace("{PROJECTPATH}", referencePath));
        ProcessStartInfo startInfo =
            new()
            {
                FileName = "dotnet",
                Arguments = "build",
                UseShellExecute = true,
                CreateNoWindow = true,
                WindowStyle = ProcessWindowStyle.Hidden,
                WorkingDirectory = projectDirectory.FullName,
            };
        this.Output.WriteLine($"BUILDING PROJECT AT: {projectDirectory.FullName}\n");
        using Process? buildProcess = Process.Start(startInfo);
        Assert.NotNull(buildProcess);
        buildProcess.WaitForExit();
        string logPath = Path.Combine(projectDirectory.FullName, "build.log");
        if (File.Exists(logPath))
        {
            this.Output.WriteLine(File.ReadAllText(logPath));
        }
        Assert.Equal(0, buildProcess.ExitCode);

        static string GetRepoFolder()
        {
            DirectoryInfo? current = new(Directory.GetCurrentDirectory());

            while (current is not null)
            {
                if (Directory.Exists(Path.Combine(current.FullName, ".git")))
                {
                    return current.FullName;
                }

                current = current.Parent;
            }

            Assert.Fail("Could not find repository root folder.");
            return string.Empty;
        }
    }
}
