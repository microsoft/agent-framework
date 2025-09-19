// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows;

namespace WorkflowHumanInTheLoopBasicSample;

/// <summary>
/// This sample introduces the concept of InputPort and ExternalRequest to enable
/// human-in-the-loop interaction scenarios.
/// An input port can be used as if it were an executor in the workflow graph. Upon receiving
/// a message, the input port generates an RequestInfoEvent that gets emitted to the external world.
/// The external world can then respond to the request by sending an ExternalResponse back to
/// the workflow.
/// The sample implements a simple number guessing game where the external user tries to guess
/// a pre-defined target number. The workflow consists of a single JudgeExecutor that judges
/// the user's guesses and provides feedback.
/// </summary>
/// <remarks>
/// Pre-requisites:
/// - Foundational samples should be completed first.
/// </remarks>
public static class Program
{
    private static async Task Main()
    {
        // Create the workflow
        var workflow = WorkflowHelper.GetWorkflow();

        // Execute the workflow
        StreamingRun handle = await InProcessExecution.StreamAsync(workflow, NumberSignal.Init).ConfigureAwait(false);
        await foreach (WorkflowEvent evt in handle.WatchStreamAsync().ConfigureAwait(false))
        {
            switch (evt)
            {
                case RequestInfoEvent requestInputEvt:
                    // Handle `RequestInfoEvent` from the workflow
                    ExternalResponse response = HandleExternalRequest(requestInputEvt.Request);
                    await handle.SendResponseAsync(response).ConfigureAwait(false);
                    break;

                case WorkflowCompletedEvent workflowCompleteEvt:
                    // The workflow has completed successfully
                    Console.WriteLine($"Workflow completed with result: {workflowCompleteEvt.Data}");
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
}
