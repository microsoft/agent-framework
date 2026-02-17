// Copyright (c) Microsoft. All rights reserved.

using System.Linq;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Abstractions.UnitTests;

/// <summary>
/// Unit tests for <see cref="AIContext"/>.
/// </summary>
public class AIContextTests
{
    [Fact]
    public void SetInstructionsRoundtrips()
    {
        var context = new AIContext
        {
            Instructions = "Test Instructions"
        };

        Assert.Equal("Test Instructions", context.Instructions);
    }

    [Fact]
    public void SetMessagesRoundtrips()
    {
        var context = new AIContext
        {
            Messages =
            [
                new(ChatRole.User, "Hello"),
                new(ChatRole.Assistant, "Hi there!")
            ]
        };

        Assert.NotNull(context.Messages);
        var messages = context.Messages.ToList();
        Assert.Equal(2, messages.Count);
        Assert.Equal("Hello", messages[0].Text);
        Assert.Equal("Hi there!", messages[1].Text);
    }

    [Fact]
    public void SetAIFunctionsRoundtrips()
    {
        var context = new AIContext
        {
            Tools =
            [
                AIFunctionFactory.Create(() => "Function1", "Function1", "Description1"),
                AIFunctionFactory.Create(() => "Function2", "Function2", "Description2"),
            ]
        };

        Assert.NotNull(context.Tools);
        var tools = context.Tools.ToList();
        Assert.Equal(2, tools.Count);
        Assert.Equal("Function1", tools[0].Name);
        Assert.Equal("Function2", tools[1].Name);
    }
}
