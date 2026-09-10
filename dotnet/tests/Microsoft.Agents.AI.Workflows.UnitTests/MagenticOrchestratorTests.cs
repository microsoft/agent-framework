// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using Microsoft.Agents.AI.Workflows.Specialized.Magentic;
using Microsoft.Extensions.AI;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

public class MagenticOrchestratorTests
{
    [Fact]
    public void Test_MagenticOrchestrator_Protocol_Declares_SentMessages()
    {
        TestReplayAgent manager = new(name: nameof(MagenticOrchestrator));
        TestEchoAgent participant = new(name: "Echo");
        MagenticOrchestrator orchestrator = new(manager, [participant], new(), requirePlanSignoff: false);

        ProtocolDescriptor protocol = orchestrator.DescribeProtocol();

        Assert.Contains(typeof(List<ChatMessage>), protocol.Sends);
        Assert.Contains(typeof(ChatMessage), protocol.Sends);
        Assert.Contains(typeof(TurnToken), protocol.Sends);
        Assert.Contains(typeof(ResetChatSignal), protocol.Sends);
    }
}
