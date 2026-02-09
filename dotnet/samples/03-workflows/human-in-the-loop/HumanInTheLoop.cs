// Copyright (c) Microsoft. All rights reserved.
// Description: Pause workflow for human input using RequestPort and ExternalRequest.
// Docs: https://learn.microsoft.com/agent-framework/workflows/overview

using Microsoft.Agents.AI.Workflows;

namespace WorkflowSamples.HumanInTheLoop;

// <human_in_the_loop_workflow>
/// <summary>
/// Demonstrates human-in-the-loop interaction using RequestPort and ExternalRequest.
/// Implements a number guessing game where the external user provides guesses
/// and the workflow provides feedback until the correct number is found.
/// </summary>
public static class Program
{
    private static async Task Main()
    {
        // Create the workflow
        var workflow = BuildWorkflow();

        // Execute the workflow
        await using StreamingRun handle = await InProcessExecution.StreamAsync(workflow, NumberSignal.Init);
        await foreach (WorkflowEvent evt in handle.WatchStreamAsync())
        {
            switch (evt)
            {
                case RequestInfoEvent requestInputEvt:
                    ExternalResponse response = HandleExternalRequest(requestInputEvt.Request);
                    await handle.SendResponseAsync(response);
                    break;

                case WorkflowOutputEvent outputEvt:
                    Console.WriteLine($"Workflow completed with result: {outputEvt.Data}");
                    return;
            }
        }
    }

    private static ExternalResponse HandleExternalRequest(ExternalRequest request)
    {
        if (request.DataIs<NumberSignal>())
        {
            switch (request.DataAs<NumberSignal>())
            {
                case NumberSignal.Init:
                    int initialGuess = ReadIntegerFromConsole("Please provide your initial guess: ");
                    return request.CreateResponse(initialGuess);
                case NumberSignal.Above:
                    int lowerGuess = ReadIntegerFromConsole("You previously guessed too large. Please provide a new guess: ");
                    return request.CreateResponse(lowerGuess);
                case NumberSignal.Below:
                    int higherGuess = ReadIntegerFromConsole("You previously guessed too small. Please provide a new guess: ");
                    return request.CreateResponse(higherGuess);
            }
        }

        throw new NotSupportedException($"Request {request.PortInfo.RequestType} is not supported");
    }

    private static int ReadIntegerFromConsole(string prompt)
    {
        while (true)
        {
            Console.Write(prompt);
            string? input = Console.ReadLine();
            if (int.TryParse(input, out int value))
            {
                return value;
            }
            Console.WriteLine("Invalid input. Please enter a valid integer.");
        }
    }
// </human_in_the_loop_workflow>

// <human_in_the_loop_factory>
    internal static Workflow BuildWorkflow()
    {
        RequestPort numberRequestPort = RequestPort.Create<NumberSignal, int>("GuessNumber");
        JudgeExecutor judgeExecutor = new(42);

        return new WorkflowBuilder(numberRequestPort)
            .AddEdge(numberRequestPort, judgeExecutor)
            .AddEdge(judgeExecutor, numberRequestPort)
            .WithOutputFrom(judgeExecutor)
            .Build();
    }
}

internal enum NumberSignal
{
    Init,
    Above,
    Below,
}

internal sealed class JudgeExecutor() : Executor<int>("Judge")
{
    private readonly int _targetNumber;
    private int _tries;

    public JudgeExecutor(int targetNumber) : this()
    {
        this._targetNumber = targetNumber;
    }

    public override async ValueTask HandleAsync(int message, IWorkflowContext context, CancellationToken cancellationToken = default)
    {
        this._tries++;
        if (message == this._targetNumber)
        {
            await context.YieldOutputAsync($"{this._targetNumber} found in {this._tries} tries!", cancellationToken);
        }
        else if (message < this._targetNumber)
        {
            await context.SendMessageAsync(NumberSignal.Below, cancellationToken: cancellationToken);
        }
        else
        {
            await context.SendMessageAsync(NumberSignal.Above, cancellationToken: cancellationToken);
        }
    }
}
// </human_in_the_loop_factory>
