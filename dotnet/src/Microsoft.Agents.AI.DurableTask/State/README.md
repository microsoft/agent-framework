# Durable Agent State

Durable agents are represented as durable entities, with each session (i.e. thread) of conversation history stored as JSON-serialized state for an individual entity instance.

## State Schema

The [schema](../../../../schemas/durable-agent-entity-state.json) for durable agent state is a distillation of the prompt and response messages accumulated over the lifetime of a session. While these messages and content originate from Microsoft Agent Framework types (for .NET, see [ChatMessage](https://github.com/dotnet/extensions/blob/main/src/Libraries/Microsoft.Extensions.AI.Abstractions/ChatCompletion/ChatMessage.cs) and [AIContent](https://github.com/dotnet/extensions/blob/main/src/Libraries/Microsoft.Extensions.AI.Abstractions/Contents/AIContent.cs)), durable agent state uses its own, parallel, types in order to (1) better manage the versioning and compatibility of serialized state over time, (2) account for agent implementations across languages/platforms (e.g. .NET and Python), as well as (3) ensure consistency for external tools that make use of state data.

> When new AI content types are added to the Microsoft Agent Framework, equivalent types should be added to the entity state schema as well. The durable agent state "unknown" type can be used when an AI content type is encountered but no equivalent type exists.

## State Versioning

The serialized state contains a root `schemaVersion` property, which represents the version of the schema used to serialize data in that state (represented by the `data` property).

Some versioning considerations:

- Versions should use semver notation (e.g. `"<major>.<minor>.<patch>"`)
- Durable agents should use the version property to determine how to deserialize that state and should not attempt to deserialize semver-incompatible versions
- Newer versions of durable agents should strive to be compatible with older schema versions (e.g. new properties and objects should be optional)
- Durable agents should preserve existing, but unrecognized, properties when serializing state

## Sample State

```json
{
  "schemaVersion": "1.0.0",
  "data": {
    "conversationHistory": [
      {
        "$type": "request",
        "responseType": "text",
        "correlationId": "c338f064f4b44b8d9c21a66e3cda41b2",
        "createdAt": "2025-11-04T19:33:05.245476+00:00",
        "messages": [
          {
            "contents": [
              {
                "$type": "text",
                "text": "Start the documentation generation workflow for the product \u0027Goldbrew Coffee\u0027"
              }
            ],
            "role": "user"
          }
        ]
      },
      {
        "$type": "response",
        "usage": {
          "inputTokenCount": 595,
          "outputTokenCount": 63,
          "totalTokenCount": 658
        },
        "correlationId": "c338f064f4b44b8d9c21a66e3cda41b2",
        "createdAt": "2025-11-04T19:33:10.47008+00:00",
        "messages": [
          {
            "authorName": "OrchestratorAgent",
            "createdAt": "2025-11-04T19:33:10+00:00",
            "contents": [
              {
                "$type": "functionCall",
                "arguments": {
                  "productName": "Goldbrew Coffee"
                },
                "callId": "call_qWk9Ay4doKYrUBoADK8MBwHf",
                "name": "StartDocumentGeneration"
              }
            ],
            "role": "assistant"
          },
          {
            "authorName": "OrchestratorAgent",
            "createdAt": "2025-11-04T19:33:10.47008+00:00",
            "contents": [
              {
                "$type": "functionResult",
                "callId": "call_qWk9Ay4doKYrUBoADK8MBwHf",
                "result": "8b835e8f2a6f40faabdba33bd8fd8c74"
              }
            ],
            "role": "tool"
          },
          {
            "authorName": "OrchestratorAgent",
            "createdAt": "2025-11-04T19:33:10+00:00",
            "contents": [
              {
                "$type": "text",
                "text": "The documentation generation workflow for the product \u0022Goldbrew Coffee\u0022 has been started. You can request updates on its status or provide additional input anytime during the process. Let me know how you\u2019d like to proceed!"
              }
            ],
            "role": "assistant"
          }
        ]
      },
      {
        "$type": "request",
        "responseType": "text",
        "correlationId": "71f35b7add6b403fadd0db8a7c137b58",
        "createdAt": "2025-11-04T19:33:11.903413+00:00",
        "messages": [
          {
            "contents": [
              {
                "$type": "text",
                "text": "Tell the user that you\u0027re starting to gather information for product \u0027Goldbrew Coffee\u0027."
              }
            ],
            "role": "system"
          }
        ]
      },
      {
        "$type": "response",
        "usage": {
          "inputTokenCount": 396,
          "outputTokenCount": 48,
          "totalTokenCount": 444
        },
        "correlationId": "71f35b7add6b403fadd0db8a7c137b58",
        "createdAt": "2025-11-04T19:33:12+00:00",
        "messages": [
          {
            "authorName": "OrchestratorAgent",
            "createdAt": "2025-11-04T19:33:12+00:00",
            "contents": [
              {
                "$type": "text",
                "text": "I am starting to gather information to create product documentation for \u0027Goldbrew Coffee\u0027. If you have any specific details, key features, or requirements you\u0027d like included, please share them. Otherwise, I\u0027ll continue with the standard documentation process."
              }
            ],
            "role": "assistant"
          }
        ]
      }
    ]
  }
}
```

## State Consumers

Additional tools may make use of durable agent state. Significant changes to the state schema may need corresponding changes to those applications.

### Durable Task Scheduler Dashboard

The [Durable Task Scheduler (DTS)](https://learn.microsoft.com/azure/azure-functions/durable/durable-task-scheduler/durable-task-scheduler) Dashboard, while providing general UX for management of durable orchestrations and entities, also has UX specific to the use of durable agents.
