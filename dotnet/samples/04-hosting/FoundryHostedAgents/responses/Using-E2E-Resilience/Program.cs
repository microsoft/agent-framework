// Copyright (c) Microsoft. All rights reserved.

// Demonstrates workflow recovery and service-side idempotency across process interruptions.
// Sample only, not a production implementation. Repeated stream text is displayed, not used to execute operations.

using Hosted_Shared_Contributor_Setup;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using static ServerManager;

if (args is ["--idempotent-service", .. var serviceArgs])
{
    await IdempotentService.RunAsync(serviceArgs);
    return;
}

using var cancellationSource = new CancellationTokenSource(TimeSpan.FromMinutes(6));
string interruptNumberMessage = "10";

try
{
    await RunScenarioAsync(interruptNumberMessage, InterruptionKind.Crash, cancellationSource.Token);
    await RunScenarioAsync(interruptNumberMessage, InterruptionKind.Shutdown, cancellationSource.Token);

    Console.WriteLine();
    Console.ForegroundColor = ConsoleColor.Green;
    Console.WriteLine("PASS: both recovery paths completed with every countdown operation stored once in SQLite.");
    Console.ResetColor();
}
catch (Exception exception)
{
    Console.WriteLine();
    Console.ForegroundColor = ConsoleColor.Red;
    Console.Error.WriteLine($"FAIL: {exception.Message}");
    Console.ResetColor();
    System.Environment.ExitCode = 1;
}

static async Task RunScenarioAsync(
    string interruptNumberMessage,
    InterruptionKind interruptionKind,
    CancellationToken cancellationToken)
{
    await using var serverManager = new ServerManager(interruptionKind);

    PrintHeader(interruptionKind, serverManager);

    Console.WriteLine($"[{interruptionKind} 1/6] Building the hosted server...");
    await serverManager.BuildServerAsync(cancellationToken);

    Console.WriteLine($"[{interruptionKind} 2/6] Starting the idempotent service and hosted server...");
    Console.WriteLine($"      Idempotent service Process ID: {await serverManager.StartIdempotentServiceAsync(cancellationToken)}");
    Console.WriteLine($"      Hosted server Process ID: {await serverManager.StartHostedAgentServerAsync(cancellationToken)}");

    AIAgent agent = serverManager.GetAIAgent();
    AgentSession session = await agent.CreateSessionAsync(cancellationToken);
    IdempotentServiceClient idempotentService = new(new HttpClient { BaseAddress = serverManager.IdempotentServiceBaseAddress });

    Console.WriteLine($"[{interruptionKind} 3/6] Starting the background response...");

    ResponseContinuationToken responseToken;
    await using (var response = agent.RunStreamingAsync(
        interruptNumberMessage, session, new AgentRunOptions { AllowBackgroundResponses = true }, cancellationToken)
        .GetAsyncEnumerator(cancellationToken))
    {
        if (!await response.MoveNextAsync())
        {
            throw new InvalidOperationException("The background response ended before it was accepted.");
        }

        responseToken = response.Current.ContinuationToken
            ?? throw new InvalidOperationException("The accepted response did not provide a continuation token.");
    }

    Console.WriteLine($"[{interruptionKind} 4/6] Waiting for operation {interruptNumberMessage}...");

    var followOptions = new AgentRunOptions
    {
        AllowBackgroundResponses = true,
        ContinuationToken = responseToken,
    };

    try
    {
        await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(session, followOptions, cancellationToken))
        {
            if (!string.IsNullOrEmpty(update.Text))
            {
                Console.WriteLine($"      {update.Text}");
            }

            if (update.Text.Contains(interruptNumberMessage, StringComparison.OrdinalIgnoreCase))
            {
                if (interruptionKind == InterruptionKind.Crash)
                {
                    Console.WriteLine("      Killing / crashing the server ...");
                    await serverManager.CrashServerAsync();
                    serverManager.DeleteStaleStreamLocks();
                }
                else
                {
                    Console.WriteLine("      Shutting down the server ...");
                    await serverManager.RequestShutdownAsync(cancellationToken);
                    await serverManager.WaitForServerExitAsync(cancellationToken);
                }
            }
        }
    }
    catch
    {
        Console.WriteLine("      The connection was interrupted.");
    }

    Console.WriteLine($"[{interruptionKind} 5/6] Starting the replacement server...");
    Console.WriteLine($"      Process ID: {await serverManager.StartHostedAgentServerAsync(cancellationToken)}");

    Console.WriteLine($"[{interruptionKind} 6/6] Reading the recovered response...");
    var recoveryOptions = new AgentRunOptions
    {
        AllowBackgroundResponses = true,
        ContinuationToken = responseToken,
    };

    List<string> textUpdates = [];
    await foreach (AgentResponseUpdate update in agent.RunStreamingAsync(session, recoveryOptions, cancellationToken))
    {
        if (!string.IsNullOrEmpty(update.Text))
        {
            Console.WriteLine($"      {update.Text}{(textUpdates.Contains(update.Text) ? " > Repeated due to abrupt crash and recovery replay (idempotency matters here)" : "")}");
            textUpdates.Add(update.Text);
        }
    }

    int operationCount = await idempotentService.GetOperationCountAsync(serverManager.OperationScope, cancellationToken);
    Console.WriteLine($"      Idempotent service contains {operationCount} completed operations.");
    serverManager.MarkSucceeded();
}

static void PrintHeader(InterruptionKind interruptionKind, ServerManager harness)
{
    Console.WriteLine();
    Console.ForegroundColor = ConsoleColor.Cyan;
    Console.WriteLine("============================================================");
    Console.WriteLine($"Running {(interruptionKind == InterruptionKind.Crash ? "Abrupt process crash" : "Host shutdown")} scenario ... ");
    Console.WriteLine("============================================================");
    Console.ResetColor();
    Console.WriteLine();
}
