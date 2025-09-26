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

public class SampleSmokeTest
{
    [Fact]
    public async Task Test_RunSample_Step1Async()
    {
        using StringWriter writer = new();

        await Step1EntryPoint.RunAsync(writer);

        string result = writer.ToString();
        string[] lines = result.Split([Environment.NewLine], StringSplitOptions.RemoveEmptyEntries);

        const string INPUT = "Hello, World!";

        Assert.Collection(lines,
            line => Assert.Contains($"UppercaseExecutor: {INPUT.ToUpperInvariant()}", line),
            line => Assert.Contains($"ReverseTextExecutor: {new string(INPUT.ToUpperInvariant().Reverse().ToArray())}", line)
        );
    }

    [Fact]
    public async Task Test_RunSample_Step1aAsync()
    {
        using StringWriter writer = new();

        await Step1aEntryPoint.RunAsync(writer);

        string result = writer.ToString();
        string[] lines = result.Split([Environment.NewLine], StringSplitOptions.RemoveEmptyEntries);

        const string INPUT = "Hello, World!";

        Assert.Collection(lines,
            line => Assert.Contains($"UppercaseExecutor: {INPUT.ToUpperInvariant()}", line),
            line => Assert.Contains($"ReverseTextExecutor: {string.Concat(INPUT.ToUpperInvariant().Reverse())}", line)
        );
    }

    [Fact]
    public async Task Test_RunSample_Step2Async()
    {
        using StringWriter writer = new();

        string spamResult = await Step2EntryPoint.RunAsync(writer);

        Assert.Equal(RemoveSpamExecutor.ActionResult, spamResult);

        string nonSpamResult = await Step2EntryPoint.RunAsync(writer, "This is a valid message.");

        Assert.Equal(RespondToMessageExecutor.ActionResult, nonSpamResult);
    }

    [Fact]
    public async Task Test_RunSample_Step3Async()
    {
        using StringWriter writer = new();

        string guessResult = await Step3EntryPoint.RunAsync(writer);

        Assert.Equal("Guessed the number: 42", guessResult);
    }

    [Fact]
    public async Task Test_RunSample_Step4Async()
    {
        using StringWriter writer = new();

        VerifyingPlaybackResponder<string, int> responder = new(
            ("Guess the number.", 50),
            ("Your guess was too high. Try again.", 23),
            ("Your guess was too low. Try again.", 42));

        string guessResult = await Step4EntryPoint.RunAsync(writer, userGuessCallback: responder.InvokeNext);
        Assert.Equal("You guessed correctly! You Win!", guessResult);
    }

    [Fact]
    public async Task Test_RunSample_Step5Async()
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

        string guessResult = await Step5EntryPoint.RunAsync(writer, userGuessCallback: responder.InvokeNext);
        Assert.Equal("You guessed correctly! You Win!", guessResult);
    }

    [Fact]
    public async Task Test_RunSample_Step5aAsync()
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

        string guessResult = await Step5EntryPoint.RunAsync(writer, userGuessCallback: responder.InvokeNext, rehydrateToRestore: true);
        Assert.Equal("You guessed correctly! You Win!", guessResult);
    }

    [Fact]
    public async Task Test_RunSample_Step5bAsync()
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
        string guessResult = await Step5EntryPoint.RunAsync(writer, userGuessCallback: responder.InvokeNext, rehydrateToRestore: true, checkpointManager: memoryJsonManager);
        Assert.Equal("You guessed correctly! You Win!", guessResult);
    }

    [Fact]
    public async Task Test_RunSample_Step6Async()
    {
        using StringWriter writer = new();

        await Step6EntryPoint.RunAsync(writer);

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

    [Fact]
    public async Task Test_RunSample_Step8Async()
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

        List<TextProcessingResult> results = await Step8EntryPoint.RunAsync(writer, textsToProcess);
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
