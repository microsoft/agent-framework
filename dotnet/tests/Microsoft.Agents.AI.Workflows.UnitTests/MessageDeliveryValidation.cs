// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
using FluentAssertions;
using Microsoft.Agents.AI.Workflows.Execution;

namespace Microsoft.Agents.AI.Workflows.UnitTests;

internal static class MessageDeliveryValidation
{
    public static void CheckDeliveries(this DeliveryMapping mapping, HashSet<string> receiverIds, HashSet<object> messages)
    {
        HashSet<string> unseenReceivers = [.. receiverIds];
        HashSet<object> unseenMessages = [.. messages];

        foreach (IGrouping<string, MessageDelivery> grouping in mapping.Deliveries.GroupBy(delivery => delivery.TargetId))
        {
            string receiverId = grouping.Key;

            receiverIds.Should().Contain(receiverId);
            unseenReceivers.Remove(grouping.Key);

            foreach (MessageDelivery delivery in grouping)
            {
                object messageValue;
                if (delivery.Envelope.Message is PortableValue portableValue)
                {
                    portableValue.IsDelayedDeserialization.Should().BeFalse();
                    messageValue = portableValue.Value;
                }
                else
                {
                    messageValue = delivery.Envelope.Message;
                }

                messages.Should().Contain(messageValue);
                unseenMessages.Remove(messageValue);
            }
        }

        unseenReceivers.Should().BeEmpty();
        unseenMessages.Should().BeEmpty();
    }

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
