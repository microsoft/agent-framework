# DecisionChat

The provider-neutral engine of a chat client for a decision model: a model that answers typed Binary, Choice, and
Score questions about a state with probabilities, instead of writing text. It is built on the decision API proposed for
`Microsoft.Extensions.AI` and works with any `IDecisionClient`, so Jev, Azure OpenAI Decisions, and other decision
models share one implementation.

- `DecisionChatEngine` answers a chat request: it sends the conversation as the state, together with the caller's
  questions and the internal questions that choose a tool call, and returns a `FunctionCallContent` or the answers.
  It rejects options that need generated text, such as `Temperature` or streaming.
- `DecisionChatState` converts a conversation into the state (`{"messages", "instructions"}`, the shape of the Python
  TypeSafe connector) and finds the current turn.
- `DecisionToolCallCompiler` turns function tools whose arguments come from a closed set (constants, enums, Booleans,
  and arrays of enum values) into a route Choice and one question per argument, with the question IDs, limits, and
  wording of the Python TypeSafe connector. `DecisionToolCallPlan` decodes the answers into the call.

A provider's public chat client converts its own question types into `DecisionQuestion` values and describes the
answers in its own result type through `DecisionChatEngineOptions.DescribeAnswers`. `JevChatClient` in
`Microsoft.Agents.AI.TypeSafe` is the first one.

## Usage

```xml
<PropertyGroup>
  <InjectSharedDecisionChat>true</InjectSharedDecisionChat>
  <InjectSharedThrow>true</InjectSharedThrow>
  <NoWarn>$(NoWarn);MEAI001</NoWarn>
</PropertyGroup>
```

The project also needs the decision API. Until `Microsoft.Extensions.AI` ships it, the only copy is in
`Microsoft.Agents.AI.TypeSafe/MEAI`, so that package is the only one that can inject the engine today. It also needs
package references to `Microsoft.Extensions.AI.Abstractions` and `Microsoft.Extensions.Logging.Abstractions`, and a
project reference to `Microsoft.Agents.AI.Abstractions`. The code targets .NET 8 and later.

The engine uses only the public surface of the decision API. Keep it that way, so it compiles unchanged once the API
ships in `Microsoft.Extensions.AI`. At that point the engine can become a public type in an Agent Framework package.
