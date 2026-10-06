# Agent with TypeSafe (Jev)

This sample uses `JevChatClient` from `Microsoft.Agents.AI.TypeSafe`, an `IChatClient` for Jev, the TypeSafe System
One model. Jev does not write text. It answers typed questions about the conversation and returns calibrated
probabilities:

| Question type | What it answers | Answer |
| --- | --- | --- |
| `JevChoiceQuestion` | Which of these named alternatives? | The selected label, the probability of each label, and a confidence |
| `JevScoreQuestion` | Which score on an ordered rubric (2 to 10 entries)? | An expected score that can fall between rubric entries, the probability of each score, and a confidence |
| `JevNoulQuestion` | Yes or no? | The probability, from 0 to 1, of yes |

The client follows the TypeSafe connector for Python (`agent-framework-typesafe`), so both languages behave alike.

## What the sample shows

1. **The chat client directly.** `WithJevQuestions` puts the questions in `ChatOptions`, and `GetJevResult` reads the
   typed answers from the response:

   ```csharp
   IChatClient client = new JevChatClient(new ApiKeyCredential(apiKey));
   ChatResponse response = await client.GetResponseAsync(ticket, new ChatOptions().WithJevQuestions(questions));
   JevResult result = response.GetJevResult()!;
   ```

   The response text is the same result as JSON, so code that reads only text still gets every answer.

2. **The client behind an agent.** A `ChatClientAgentRunOptions` carries the questions for one run. Questions in the
   agent's `ChatClientAgentOptions.ChatOptions` apply to every run, and a run's questions replace them.

3. **Default questions.** A client created with `JevChatClientOptions.DefaultQuestions` answers requests that pass no
   questions, so code that knows nothing about Jev can use it like any other `IChatClient`. The sample runs an agent
   without any Jev options.

4. **Function calling.** Jev cannot write arguments, so the client adds internal questions that choose the tool and
   each argument from a closed set: a constant, an enum, a Boolean, or an array of enum values. Optional arguments
   are passed only when Jev decides the user asked for them; here, the temperature unit is passed because the user
   asks for Fahrenheit. The agent runs the tool, and once the turn has used
   `JevChatClientOptions.MaximumToolCallsPerTurn` calls (one by default, two in this sample), the client answers the
   caller's questions with the tool results in the state. The response text is then the tool results followed by one
   `id: answer` line per Choice and Score answer:

   ```text
   Seattle is sunny and 75 F with a detailed hourly forecast.
   Amsterdam is sunny and 69 F with a detailed hourly forecast.
   better_city: Seattle
   ```

   Jev reads each tool's name and description, and each argument's description, to make these choices, so write them
   for Jev as you would for a person. Give local functions an explicit name, because their compiler-generated names
   mean nothing. In this sample, saying that `detailed` is true "when the user asks for a detailed report" is what makes
   Jev choose it reliably. Tools with free-form arguments, such as text or numbers, are left out of the request with a
   warning in the log.

5. **Tool approval.** A tool wrapped in `ApprovalRequiredAIFunction` runs only after the user approves the call that
   Jev chose. The first run returns a `ToolApprovalRequestContent`; the sample asks for approval in the console and
   sends the answer in a second run on the same session, with the same questions.

## Limits

Jev answers all questions at once, so the client rejects what needs generated text: streaming (`RunStreamingAsync`),
sampling and output options such as `Temperature` or a JSON `ResponseFormat`, server-side conversations, tools other
than functions, and message content other than text, reasoning text, and function calls and results. Each fails with a
`NotSupportedException` that names the problem. Tool approval requests and responses are allowed but left out of what
Jev reads, because the call and result they lead to carry the information.

Because streaming is not supported, run agents with `RunAsync`. A function-invoking client runs approved tools before
it calls the chat client, so a streaming run that resumes a tool approval would run the tool and then fail.

## Configuring the client

`JevChatClientOptions` follows the `ClientPipelineOptions` pattern of the OpenAI and Azure AI client libraries, with the
retry and timeout defaults of the official TypeSafe SDK:

```csharp
var options = new JevChatClientOptions
{
    ModelId = "jev-latest",                 // ChatOptions.ModelId overrides it per request
    MaximumToolCallsPerTurn = 2,
    Transport = new HttpClientPipelineTransport(httpClientFactory.CreateClient("jev")),
};
IChatClient client = new JevChatClient(new ApiKeyCredential(apiKey), options);
```

To use Jev as a tool of an agent whose own model writes the replies, see
[Classification with Jev](../../../Agents/Agent_Step25_ClassificationWithJev/). To use it as the judge of a
`LoopAgent`, see [Jev as the judge of a loop](../Agent_TypeSafe_Step01_LoopJudge/).

## Prerequisites

- .NET 10 SDK or later
- A TypeSafe API key

Set the environment variable:

```powershell
$env:TYPESAFE_API_KEY="your-typesafe-api-key"
```

## Running the sample

```powershell
dotnet run
```

The tool approval step asks for `Y` or `N` in the console. Probabilities, scores, and the temperatures in the tool
results vary between runs.
