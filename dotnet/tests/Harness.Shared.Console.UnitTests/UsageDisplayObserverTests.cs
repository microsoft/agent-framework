// Copyright (c) Microsoft. All rights reserved.

using System.Threading.Tasks;
using Harness.Shared.Console;
using Harness.Shared.Console.Observers;
using Microsoft.Extensions.AI;
using Moq;

namespace Microsoft.Agents.AI.HarnessConsole.UnitTests;

public class UsageDisplayObserverTests
{
    [Fact]
    public async Task UsageAccumulatesAcrossCallsAndIsolatesSessionsAsync()
    {
        // Arrange
        var observer = new UsageDisplayObserver(1000, 200);
        var ux = new Mock<IUXStateDriver>();
        var agent = new Mock<AIAgent>().Object;
        var first = new Mock<AgentSession>().Object;
        var second = new Mock<AgentSession>().Object;
        string? displayed = null;
        ux.Setup(u => u.SetUsageText(It.IsAny<string>())).Callback<string>(text => displayed = text);
        var usage = new UsageDetails { InputTokenCount = 100, OutputTokenCount = 20, TotalTokenCount = 120 };

        // Act
        await observer.OnContentAsync(ux.Object, new UsageContent(usage), agent, first);
        await observer.OnContentAsync(ux.Object, new UsageContent(usage), agent, first);

        // Assert
        Assert.EndsWith("session: 240 tokens", displayed);
        Assert.Contains("input: 100/800", displayed);
        Assert.Equal(120, usage.TotalTokenCount);

        // Act
        await observer.OnContentAsync(ux.Object, new UsageContent(usage), agent, second);

        // Assert
        Assert.EndsWith("session: 120 tokens", displayed);
    }

    [Fact]
    public async Task MissingTotalUsesInputAndOutputWithoutTreatingUnknownUsageAsZeroAsync()
    {
        // Arrange
        var observer = new UsageDisplayObserver(null, null);
        var ux = new Mock<IUXStateDriver>();
        var agent = new Mock<AIAgent>().Object;
        var session = new Mock<AgentSession>().Object;
        string? displayed = null;
        ux.Setup(u => u.SetUsageText(It.IsAny<string>())).Callback<string>(text => displayed = text);

        // Act
        await observer.OnContentAsync(ux.Object, new UsageContent(new UsageDetails()), agent, session);

        // Assert
        Assert.EndsWith("session: — tokens", displayed);

        // Act
        await observer.OnContentAsync(ux.Object, new UsageContent(new UsageDetails { InputTokenCount = 7, OutputTokenCount = 3 }), agent, session);
        await observer.OnContentAsync(ux.Object, new UsageContent(new UsageDetails()), agent, session);

        // Assert
        Assert.EndsWith("session: 10 tokens", displayed);
    }
}
