// Copyright (c) Microsoft. All rights reserved.

using System.Diagnostics;
using Microsoft.Agents.AI.Workflows.Declarative;

namespace Demo.DeclarativeEject;

/// <summary>
/// HOW TO: Convert a workflow from a declartive (yaml based) definition to code.
/// </summary>
/// <remarks>
/// <b>Usage</b>
/// Provide the path to the workflow definition file as the first argument.
/// All other arguments are intepreted as a queue of inputs.
/// When no input is queued, interactive input is requested from the console.
/// </remarks>
internal sealed class Program
{
    public static void Main(string[] args)
    {
        Program program = new(args);
        program.Execute();
    }

    private void Execute()
    {
        // Read and parse the declarative workflow.
        Notify($"WORKFLOW: Parsing {Path.GetFullPath(this.WorkflowFile)}");

        Stopwatch timer = Stopwatch.StartNew();

        // Use DeclarativeWorkflowBuilder to generate code based on a YAML file.
        string code =
            DeclarativeWorkflowBuilder.Eject(
                this.WorkflowFile,
                DeclarativeWorkflowLanguage.CSharp,
                workflowNamespace: "Demo.DeclarativeCode",
                workflowPrefix: "Sample");

        Notify($"\nWORKFLOW: Defined {timer.Elapsed}\n");

        Console.WriteLine(code);
    }

    private const string DefaultWorkflow = "Marketing.yaml";

    private string WorkflowFile { get; }

    private Program(string[] args)
    {
        this.WorkflowFile = ParseWorkflowFile(args);
    }

    private static string ParseWorkflowFile(string[] args)
    {
        string workflowFile = args.FirstOrDefault() ?? DefaultWorkflow;

        if (!File.Exists(workflowFile) && !Path.IsPathFullyQualified(workflowFile))
        {
            string? repoFolder = GetRepoFolder();
            if (repoFolder is not null)
            {
                workflowFile = Path.Combine(repoFolder, "workflow-samples", workflowFile);
                workflowFile = Path.ChangeExtension(workflowFile, ".yaml");
            }
        }

        if (!File.Exists(workflowFile))
        {
            throw new InvalidOperationException($"Unable to locate workflow: {Path.GetFullPath(workflowFile)}.");
        }

        return workflowFile;

        static string? GetRepoFolder()
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

            return null;
        }
    }

    private static void Notify(string message)
    {
        Console.ForegroundColor = ConsoleColor.Cyan;
        try
        {
            Console.WriteLine(message);
        }
        finally
        {
            Console.ResetColor();
        }
    }
}
