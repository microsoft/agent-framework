// Copyright (c) Microsoft. All rights reserved.

using System;
using System.Collections.Generic;
using System.Linq;
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

            Assert.Contains(receiverId, receiverIds);
            unseenReceivers.Remove(grouping.Key);

            foreach (MessageDelivery delivery in grouping)
            {
                object messageValue;
                if (delivery.Envelope.Message is PortableValue portableValue)
                {
                    Assert.False(portableValue.IsDelayedDeserialization);
                    messageValue = portableValue.Value;
                }
                else
                {
                    messageValue = delivery.Envelope.Message;
                }

                Assert.Contains(messageValue, messages);
                unseenMessages.Remove(messageValue);
            }
        }

        Assert.Empty(unseenReceivers ?? []);
        Assert.Empty(unseenMessages ?? []);
    }

    public static void CheckForwarded(Dictionary<string, List<MessageEnvelope>> queuedMessages, params (string expectedSender, List<string> expectedMessages)[] expectedForwards)
    {
        Assert.Equal(expectedForwards.Length, queuedMessages.Count);

        IEnumerable<Action<string>> perSenderValidations = expectedForwards.Select(
                (forward) =>
                {
                    (string expectedSender, List<string> expectedMessages) = forward;

                    return (Action<string>)(
                        senderId =>
                        {
                            Assert.Equal(expectedSender, senderId);
                            Assert.Equal(expectedMessages.Count, queuedMessages[senderId].Count);

                            Action<MessageEnvelope>[] validations
                                = expectedMessages.Select(message => (Action<MessageEnvelope>)(envelope => Assert.Equal(message, envelope!.Message)))
                                                  .ToArray();

                            Assert.Collection(queuedMessages[senderId], validations);
                        });
                }
            );

        Assert.Collection(queuedMessages.Keys, perSenderValidations.ToArray());
    }
}
