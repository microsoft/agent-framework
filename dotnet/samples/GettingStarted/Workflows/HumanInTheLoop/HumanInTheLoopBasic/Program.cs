// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI.Workflows;

namespace WorkflowHumanInTheLoopBasicSample;

/// <summary>
/// This sample introduces the concept of RequestPort and ExternalRequest to enable
/// human-in-the-loop interaction scenarios.
/// A request port can be used as if it were an executor in the workflow graph. Upon receiving
/// a message, the request port generates an RequestInfoEvent that gets emitted to the external world.
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
        var workflow = await WorkflowHelper.GetWorkflowAsync();

        // Execute the workflow
        await using StreamingRun handle = await InProcessExecution.StreamAsync(workflow, NumberSignal.Init);
        await foreach (WorkflowEvent evt in handle.WatchStreamAsync())
        {
            switch (evt)
            {
                case RequestInfoEvent requestInputEvt:
                    // Handle `RequestInfoEvent` from the workflow
                    ExternalResponse response = HandleExternalRequest(requestInputEvt.Request);
                    await handle.SendResponseAsync(response);
                    break;

                case WorkflowOutputEvent outputEvt:
                    // The workflow has yielded output
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
}
