// Copyright (c) Microsoft. All rights reserved.

using Azure.Identity;
using Microsoft.Agents.Orchestration;
using Microsoft.Agents.Workflows;
using Microsoft.Agents.Workflows.Declarative;
using Microsoft.Shared.Diagnostics;
using Microsoft.Shared.Samples;

namespace Workflows;

/// <summary>
/// Demonstrates how to use the <see cref="ConcurrentOrchestration"/>
/// for executing multiple agents on the same task in parallel.
/// </summary>
public class Workflows_Declarative(ITestOutputHelper output) : OrchestrationSample(output)
{
    [Theory]
    [InlineData("Expression.CountIf")]
    [InlineData("Expression.CountIfType")]
    [InlineData("Expression.DropColumns")]
    [InlineData("Expression.ForAll")]
    public async Task RunWorkflow(string fileName)
    {
        Console.WriteLine("WORKFLOW INIT\n");

        //////////////////////////////////////////////////////
        //
        // HOW TO: Create a workflow from a YAML file.
        //
        using StreamReader yamlReader = File.OpenText(@$"{nameof(Workflows)}\{fileName}.yaml");
        //
        // DeclarativeWorkflowContext provides the components for workflow execution.
        //
        DeclarativeWorkflowOptions workflowContext =
            new()
            {
                LoggerFactory = this.LoggerFactory,
                ProjectEndpoint = Throw.IfNull(TestConfiguration.AzureAI.Endpoint),
                ProjectCredentials = new AzureCliCredential(),
            };
        //
        // Use DeclarativeWorkflowBuilder to build a workflow based on a YAML file.
        //
        Workflow<string> workflow = DeclarativeWorkflowBuilder.Build<string>(yamlReader, workflowContext);
        //
        //////////////////////////////////////////////////////

        Console.WriteLine("\nWORKFLOW INVOKE\n");

        StreamingRun run = await InProcessExecution.StreamAsync(workflow, "<placeholder>");
        await foreach (WorkflowEvent evt in run.WatchStreamAsync().ConfigureAwait(false))
        {
            if (evt is DeclarativeWorkflowMessageEvent messageEvent)
            {
                if (messageEvent.Data.MessageId is null)
                {
                    Console.WriteLine(messageEvent.Data);
                }
                else
                {
                    Console.WriteLine($"#{messageEvent.Data.MessageId}:");
                    Console.WriteLine(messageEvent.Data);
                    if (messageEvent.Usage is not null)
                    {
                        Console.WriteLine($"[Tokens Total: {messageEvent.Usage.TotalTokenCount}, Input: {messageEvent.Usage.InputTokenCount}, Output: {messageEvent.Usage.OutputTokenCount}]");
                    }
                    Console.WriteLine();
                }
            }
        }

        Console.WriteLine("\nWORKFLOW DONE");
    }
}
