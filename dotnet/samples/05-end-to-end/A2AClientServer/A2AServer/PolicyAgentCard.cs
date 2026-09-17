// Copyright (c) Microsoft. All rights reserved.

using A2A;

namespace A2AServer;

internal static class PolicyAgentCard
{
    internal static AgentCard Create(string agentUrl)
    {
        return new()
        {
            Name = "PolicyAgent",
            Description = "Handles requests relating to policies and customer communications.",
            Version = "1.0.0",
            DefaultInputModes = ["text/plain"],
            DefaultOutputModes = ["text/plain"],
            Capabilities = new()
            {
                Streaming = false,
                PushNotifications = false,
            },
            Skills =
            [
                new()
                {
                    Id = "id_policy_agent",
                    Name = "PolicyAgent",
                    Description = "Handles requests relating to policies and customer communications.",
                    Tags = ["policy"],
                    Examples = ["What is the policy for short shipments?"],
                },
            ],
            SupportedInterfaces =
            [
                new()
                {
                    Url = agentUrl,
                    ProtocolBinding = ProtocolBindingNames.JsonRpc,
                    ProtocolVersion = "1.0",
                },
                new()
                {
                    Url = agentUrl,
                    ProtocolBinding = ProtocolBindingNames.HttpJson,
                    ProtocolVersion = "1.0",
                },
            ],
        };
    }
}
