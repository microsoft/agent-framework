// Copyright (c) Microsoft. All rights reserved.

namespace Microsoft.Extensions.AI.Agents.Abstractions.UnitTests;

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
        Assert.Equal(2, context.Messages.Count);
        Assert.Equal("Hello", context.Messages[0].Text);
        Assert.Equal("Hi there!", context.Messages[1].Text);
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
        Assert.Equal(2, context.Tools.Count);
        Assert.Equal("Function1", context.Tools[0].Name);
        Assert.Equal("Function2", context.Tools[1].Name);
    }
}
