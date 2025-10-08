// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading.Tasks;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Sample;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal enum ExecutionEnvironment
{
    InProcess_Lockstep,
    InProcess_OffThread,
    InProcess_Concurrent
}

public class SampleSmokeTest
{
    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Concurrent)]
    internal async Task Test_RunSample_Step1Async(ExecutionEnvironment environment)
    {
        using StringWriter writer = new();

        await Step1EntryPoint.RunAsync(writer, environment.ToWorkflowExecutionEnvironment());

        string result = writer.ToString();
        string[] lines = result.Split([Environment.NewLine], StringSplitOptions.RemoveEmptyEntries);

        const string INPUT = "Hello, World!";

        Assert.Collection(lines,
            line => Assert.Contains($"UppercaseExecutor: {INPUT.ToUpperInvariant()}", line),
            line => Assert.Contains($"ReverseTextExecutor: {new string(INPUT.ToUpperInvariant().Reverse().ToArray())}", line)
        );
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Concurrent)]
    internal async Task Test_RunSample_Step1aAsync(ExecutionEnvironment environment)
    {
        using StringWriter writer = new();

        await Step1aEntryPoint.RunAsync(writer, environment.ToWorkflowExecutionEnvironment());

        string result = writer.ToString();
        string[] lines = result.Split([Environment.NewLine], StringSplitOptions.RemoveEmptyEntries);

        const string INPUT = "Hello, World!";

        Assert.Collection(lines,
            line => Assert.Contains($"UppercaseExecutor: {INPUT.ToUpperInvariant()}", line),
            line => Assert.Contains($"ReverseTextExecutor: {string.Concat(INPUT.ToUpperInvariant().Reverse())}", line)
        );
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Concurrent)]
    internal async Task Test_RunSample_Step2Async(ExecutionEnvironment environment)
    {
        using StringWriter writer = new();

        string spamResult = await Step2EntryPoint.RunAsync(writer, environment.ToWorkflowExecutionEnvironment());

        Assert.Equal(RemoveSpamExecutor.ActionResult, spamResult);

        string nonSpamResult = await Step2EntryPoint.RunAsync(writer, environment.ToWorkflowExecutionEnvironment(), "This is a valid message.");

        Assert.Equal(RespondToMessageExecutor.ActionResult, nonSpamResult);
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Concurrent)]
    internal async Task Test_RunSample_Step3Async(ExecutionEnvironment environment)
    {
        using StringWriter writer = new();

        string guessResult = await Step3EntryPoint.RunAsync(writer, environment.ToWorkflowExecutionEnvironment());

        Assert.Equal("Guessed the number: 42", guessResult);
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Concurrent)]
    internal async Task Test_RunSample_Step4Async(ExecutionEnvironment environment)
    {
        using StringWriter writer = new();

        VerifyingPlaybackResponder<string, int> responder = new(
            ("Guess the number.", 50),
            ("Your guess was too high. Try again.", 23),
            ("Your guess was too low. Try again.", 42));

        string guessResult = await Step4EntryPoint.RunAsync(writer, userGuessCallback: responder.InvokeNext, environment.ToWorkflowExecutionEnvironment());
        Assert.Equal("You guessed correctly! You Win!", guessResult);
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Concurrent)]
    internal async Task Test_RunSample_Step5Async(ExecutionEnvironment environment)
    {
        using StringWriter writer = new();

        VerifyingPlaybackResponder<string, int> responder = new(
            // Iteration 1
            ("Guess the number.", 50),
            ("Your guess was too high. Try again.", 23),

            // Iteration 2
            ("Your guess was too high. Try again.", 23),
            ("Your guess was too low. Try again.", 42)
         );

        string guessResult = await Step5EntryPoint.RunAsync(writer, userGuessCallback: responder.InvokeNext, environment.ToWorkflowExecutionEnvironment());
        Assert.Equal("You guessed correctly! You Win!", guessResult);
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Concurrent)]
    internal async Task Test_RunSample_Step5aAsync(ExecutionEnvironment environment)
    {
        using StringWriter writer = new();

        VerifyingPlaybackResponder<string, int> responder = new(
            // Iteration 1
            ("Guess the number.", 50),
            ("Your guess was too high. Try again.", 23),

            // Iteration 2
            ("Your guess was too high. Try again.", 23),
            ("Your guess was too low. Try again.", 42)
         );

        string guessResult = await Step5EntryPoint.RunAsync(writer, userGuessCallback: responder.InvokeNext, environment.ToWorkflowExecutionEnvironment(), rehydrateToRestore: true);
        Assert.Equal("You guessed correctly! You Win!", guessResult);
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Concurrent)]
    internal async Task Test_RunSample_Step5bAsync(ExecutionEnvironment environment)
    {
        using StringWriter writer = new();

        VerifyingPlaybackResponder<string, int> responder = new(
            // Iteration 1
            ("Guess the number.", 50),
            ("Your guess was too high. Try again.", 23),

            // Iteration 2
            ("Your guess was too high. Try again.", 23),
            ("Your guess was too low. Try again.", 42)
         );

        JsonSerializerOptions options = new(SampleJsonContext.Default.Options);
        options.MakeReadOnly();

        CheckpointManager memoryJsonManager = CheckpointManager.CreateJson(new InMemoryJsonStore(), options);
        string guessResult = await Step5EntryPoint.RunAsync(writer, userGuessCallback: responder.InvokeNext, environment.ToWorkflowExecutionEnvironment(), rehydrateToRestore: true, checkpointManager: memoryJsonManager);
        Assert.Equal("You guessed correctly! You Win!", guessResult);
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Concurrent)]
    internal async Task Test_RunSample_Step6Async(ExecutionEnvironment environment)
    {
        using StringWriter writer = new();

        await Step6EntryPoint.RunAsync(writer, environment.ToWorkflowExecutionEnvironment());

        string result = writer.ToString();
        string[] lines = result.Split([Environment.NewLine], StringSplitOptions.RemoveEmptyEntries);

        Assert.Collection(lines,
            line => Assert.Contains($"{HelloAgent.DefaultId}: {HelloAgent.Greeting}", line),
            line => Assert.Contains($"{EchoAgent.DefaultId}: {EchoAgent.Prefix}{HelloAgent.Greeting}", line)
        );
    }

    [Fact]
    public async Task Test_RunSample_Step7Async()
    {
        using StringWriter writer = new();

        await Step7EntryPoint.RunAsync(writer);

        string result = writer.ToString();
        string[] lines = result.Split([Environment.NewLine], StringSplitOptions.RemoveEmptyEntries);

        Assert.Collection(lines,
            line => Assert.Contains($"{HelloAgent.DefaultId}: {HelloAgent.Greeting}", line),
            line => Assert.Contains($"{EchoAgent.DefaultId}: {EchoAgent.Prefix}{HelloAgent.Greeting}", line)
        );
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Concurrent)]
    internal async Task Test_RunSample_Step8Async(ExecutionEnvironment environment)
    {
        List<string> textsToProcess = [
            "Hello world! This is a simple test.",
            "Python is a powerful programming language used for many applications.",
            "Short text.",
            "This is a longer text with multiple sentences. It contains more words and characters. We use it to test our text processing workflow.",
            "",
            "   Spaces   around   text   ",
        ];

        using StringWriter writer = new();

        List<TextProcessingResult> results = await Step8EntryPoint.RunAsync(writer, environment.ToWorkflowExecutionEnvironment(), textsToProcess);
        Assert.Equal(textsToProcess.Count, results.Count);

        Assert.Collection(results,
                          textsToProcess.Select(CreateValidator).ToArray());

        Action<TextProcessingResult> CreateValidator(string textToProcess, int index)
        {
            return result =>
            {
                TextProcessingResult expected = new(
                    TaskId: $"Task{index}",
                    Text: textToProcess,
                    WordCount: textToProcess.Split([' '], StringSplitOptions.RemoveEmptyEntries).Length,
                    ChatCount: textToProcess.Length
                );

                result.Should().Be(expected);
            };
        }
    }

    [Theory]
    [InlineData(ExecutionEnvironment.InProcess_Lockstep)]
    [InlineData(ExecutionEnvironment.InProcess_OffThread)]
    [InlineData(ExecutionEnvironment.InProcess_Concurrent)]
    internal async Task Test_RunSample_Step9Async(ExecutionEnvironment environment)
    {
        using StringWriter writer = new();
        _ = await Step9EntryPoint.RunAsync(writer, environment.ToWorkflowExecutionEnvironment());
    }
}

internal sealed class VerifyingPlaybackResponder<TInput, TResponse>
{
    public (TInput input, TResponse response)[] Responses { get; }
    private int _position;

    public VerifyingPlaybackResponder(params (TInput input, TResponse response)[] responses)
    {
        this.Responses = responses;
    }

    public int Remaining => Math.Max(0, this.Responses.Length - this._position);

    public TResponse InvokeNext(TInput input)
    {
        Assert.True(this.Remaining > 0);

        (TInput expectedInput, TResponse expectedResponse) = this.Responses[this._position++];
        Assert.Equal(expectedInput, input);

        return expectedResponse;
    }
}
