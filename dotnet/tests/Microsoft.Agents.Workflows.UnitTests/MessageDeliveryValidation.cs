// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Microsoft.Agents.Workflows.Execution;

namespace Microsoft.Agents.Workflows.UnitTests;

internal static class MessageDeliveryValidation
{
    public static void CheckForwarded(Dictionary<string, List<MessageEnvelope>> queuedMessages, params (string expectedSender, List<string> expectedMessages)[] expectedForwards)
    {
        queuedMessages.Should().HaveCount(expectedForwards.Length);

        IEnumerable<Action<string>> perSenderValidations = expectedForwards.Select(
                (forward) =>
                {
                    (string expectedSender, List<string> expectedMessages) = forward;

                    return (Action<string>)(
                        senderId =>
                        {
                            senderId.Should().Be(expectedSender);
                            queuedMessages[senderId].Should().HaveCount(expectedMessages.Count);

                            Action<MessageEnvelope>[] validations
                                = expectedMessages.Select(message => (Action<MessageEnvelope>)(envelope => envelope!.Message.Should().Be(message)))
                                                  .ToArray();

                            Assert.Collection(queuedMessages[senderId], validations);
                        });
                }
            );

        Assert.Collection(queuedMessages.Keys, perSenderValidations.ToArray());
    }
}
