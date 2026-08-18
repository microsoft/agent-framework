// Copyright (c) Microsoft. All rights reserved.

using System.Collections.Generic;
using FluentAssertions;
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

        protocol.Sends.Should().Contain(typeof(List<ChatMessage>));
        protocol.Sends.Should().Contain(typeof(ChatMessage));
        protocol.Sends.Should().Contain(typeof(TurnToken));
        protocol.Sends.Should().Contain(typeof(ResetChatSignal));
    }
}
