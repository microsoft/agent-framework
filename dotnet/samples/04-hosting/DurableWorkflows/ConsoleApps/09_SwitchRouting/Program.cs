// Copyright (c) Microsoft. All rights reserved.

// This sample demonstrates multi-way routing in a workflow using AddSwitch.
// An expense is routed to a different approval path based on its amount:
// - Amount < 100      -> AutoApprove
// - Amount < 1000     -> ManagerApproval
// - Otherwise         -> DirectorApproval (default)
//
// Unlike AddEdge(..., condition:), which adds an independent boolean condition per edge,
// AddSwitch evaluates its cases in order and routes to the FIRST matching branch (or the
// default when none match), making it a natural fit for multi-way routing.

using Microsoft.Agents.AI.DurableTask;
using Microsoft.Agents.AI.DurableTask.Workflows;
using Microsoft.Agents.AI.Workflows;
using Microsoft.DurableTask.Client.AzureManaged;
using Microsoft.DurableTask.Worker.AzureManaged;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Logging;
using SwitchRouting;

string dtsConnectionString = Environment.GetEnvironmentVariable("DURABLE_TASK_SCHEDULER_CONNECTION_STRING")
    ?? "Endpoint=http://localhost:8080;TaskHub=default;Authentication=None";

// Create executor instances
ExpenseParser expenseParser = new();
AutoApprove autoApprove = new();
ManagerApproval managerApproval = new();
DirectorApproval directorApproval = new();

// Build a workflow that switches on the parsed expense amount. Cases are evaluated in order;
// the first matching case wins, and WithDefault handles everything else.
WorkflowBuilder builder = new(expenseParser);
builder.AddSwitch(expenseParser, switchBuilder =>
    switchBuilder
        .AddCase<Expense>(expense => expense!.Amount < 100m, autoApprove)
        .AddCase<Expense>(expense => expense!.Amount < 1000m, managerApproval)
        .WithDefault(directorApproval));

Workflow approveExpense = builder.WithName("ApproveExpense").Build();

IHost host = Host.CreateDefaultBuilder(args)
.ConfigureLogging(logging => logging.SetMinimumLevel(LogLevel.Warning))
.ConfigureServices(services =>
{
    services.ConfigureDurableWorkflows(
        workflowOptions => workflowOptions.AddWorkflow(approveExpense),
        workerBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString),
        clientBuilder: builder => builder.UseDurableTaskScheduler(dtsConnectionString));
})
.Build();

await host.StartAsync();

IWorkflowClient workflowClient = host.Services.GetRequiredService<IWorkflowClient>();

Console.WriteLine("Enter an expense amount (or 'exit'):");
Console.WriteLine("Tip: try 50, 450, and 5000 to see each branch.\n");

while (true)
{
    Console.Write("> ");
    string? input = Console.ReadLine();
    if (string.IsNullOrWhiteSpace(input) || input.Equals("exit", StringComparison.OrdinalIgnoreCase))
    {
        break;
    }

    try
    {
        await StartNewWorkflowAsync(input, approveExpense, workflowClient);
    }
    catch (Exception ex)
    {
        Console.WriteLine($"Error: {ex.Message}");
    }

    Console.WriteLine();
}

await host.StopAsync();

// Start a new workflow and wait for completion
static async Task StartNewWorkflowAsync(string amount, Workflow workflow, IWorkflowClient client)
{
    Console.WriteLine($"Starting workflow for expense amount '{amount}'...");

    // Cast to IAwaitableWorkflowRun to access WaitForCompletionAsync
    IAwaitableWorkflowRun run = (IAwaitableWorkflowRun)await client.RunAsync(workflow, amount);
    Console.WriteLine($"Run ID: {run.RunId}");

    try
    {
        Console.WriteLine("Waiting for workflow to complete...");
        string? result = await run.WaitForCompletionAsync<string>();
        Console.WriteLine($"Workflow completed. {result}");
    }
    catch (InvalidOperationException ex)
    {
        Console.WriteLine($"Failed: {ex.Message}");
    }
}
