// Copyright (c) Microsoft. All rights reserved.

using Azure.AI.Projects;
using Azure.Identity;
using Microsoft.Agents.AI;
using Microsoft.Agents.AI.Workflows;
using Microsoft.Extensions.AI;

string endpoint = Environment.GetEnvironmentVariable("AZURE_AI_PROJECT_ENDPOINT")
            ?? throw new InvalidOperationException("AZURE_AI_PROJECT_ENDPOINT is not set.");
string deploymentName = Environment.GetEnvironmentVariable("AZURE_AI_MODEL_DEPLOYMENT_NAME") ?? "gpt-5.4-mini";

// WARNING: DefaultAzureCredential is convenient for development but requires careful consideration in production.
// In production, consider using a specific credential (e.g., ManagedIdentityCredential) to avoid
// latency issues, unintended credential probing, and potential security risks from fallback mechanisms.
AIProjectClient projectClient = new(new Uri(endpoint), new DefaultAzureCredential());

IChatClient chatClient = projectClient.ProjectOpenAIClient
                                      .GetChatClient(deploymentName)
                                      .AsIChatClient();

Workflow workflow = CreateWorkflow(chatClient);

await RunWorkflowAsync(workflow).ConfigureAwait(false);

static Workflow CreateWorkflow(IChatClient chatClient)
{
    AgentRegistry agents = new(chatClient);

    HandoffWorkflowBuilder handoffBuilder = AgentWorkflowBuilder.CreateHandoffBuilderWith(agents.IntakeAgent);

    // Add a handoff to each of the experts from every agent in the registry (experts + Intake)
    foreach (AIAgent expert in agents.Experts)
    {
        handoffBuilder.WithHandoffs(agents.All.Except([expert]), expert);
    }

    // Let agents request more user information and return to the asking agent (rather than going back to the intake agent)
    handoffBuilder.EnableReturnToPrevious();

    return handoffBuilder.Build();
}

static async Task RunWorkflowAsync(Workflow workflow)
{
    using CancellationTokenSource cts = CreateConsoleCancelKeySource();
    await using StreamingRun run = await InProcessExecution.OpenStreamingAsync(workflow, cancellationToken: cts.Token)
                                                           .ConfigureAwait(false);

    bool hadError = false;
    do
    {
        Console.Write("> ");
        string userInput = Console.ReadLine() ?? string.Empty;

        if (userInput.Equals("exit", StringComparison.OrdinalIgnoreCase))
        {
            break;
        }

        await run.TrySendMessageAsync(userInput);
        string? speakingAgent = null;
        await foreach (WorkflowEvent evt in run.WatchStreamAsync(cts.Token))
        {
            switch (evt)
            {
                case AgentResponseUpdateEvent update:
                {
                    if (speakingAgent == null || speakingAgent != update.Update.AuthorName)
                    {
                        speakingAgent = update.Update.AuthorName;
                        Console.Write($"\n{speakingAgent}: ");
                    }

                    Console.Write(update.Update.Text);
                    break;
                }

                case WorkflowErrorEvent workflowError:
                {
                    Console.ForegroundColor = ConsoleColor.Red;

                    if (workflowError.Exception != null)
                    {
                        Console.WriteLine($"\nWorkflow error: {workflowError.Exception}");
                    }
                    else
                    {
                        Console.WriteLine("\nUnknown workflow error occurred.");
                    }

                    Console.ResetColor();

                    hadError = true;
                    break;
                }

                case WorkflowWarningEvent workflowWarning when workflowWarning.Data is string message:
                {
                    Console.ForegroundColor = ConsoleColor.Yellow;
                    Console.WriteLine(message);
                    Console.ResetColor();
                    break;
                }
            }
        }
    } while (!hadError);
}

static CancellationTokenSource CreateConsoleCancelKeySource()
{
    CancellationTokenSource cts = new();

    // Normally, support a way to detach events, but in this case this is a termination signal, so cleanup will happen
    // as part of application shutdown.
    Console.CancelKeyPress += (s, args) =>
    {
        cts.Cancel();

        // We handle cleanup + termination ourselves
        args.Cancel = true;
    };

    return cts;
}
