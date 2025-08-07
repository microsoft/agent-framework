// Copyright (c) Microsoft. All rights reserved.

using System;
using System.IO;
using System.Linq;
using System.Threading.Tasks;
using Microsoft.Agents.Workflows.Sample;

namespace Microsoft.Agents.Workflow.UnitTests;

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
}
