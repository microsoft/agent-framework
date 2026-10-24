# Classification with Jev

This sample gives an agent a classifier tool built with `JevAIToolBuilder` from `Microsoft.Agents.AI.TypeSafe`.

Jev, the TypeSafe System One model, does not write text. It answers typed questions about a state and returns
calibrated probabilities. An agent's model writes the replies; Jev makes the fast, structured decisions:

1. The agent's model calls `ask_system_one` with a Jev request: the `state` and the `questions` to
   answer about it.
2. Jev answers each question:

   | Question type | What it answers | Answer |
   | --- | --- | --- |
   | `choice` | Which of these named alternatives? | The selected label, the probability of each label, and a confidence |
   | `score` | Which score on an ordered rubric (2 to 10 entries)? | An expected score that can fall between rubric entries, the probability of each score, and a confidence |
   | `noul` | Yes or no? | The probability, from 0 to 1, of yes |

   The state, the instructions, and every criterion can be text or JSON, like `EntryType` in the official TypeSafe SDK
   ([`@typesafe-ai/sdk`](https://github.com/typesafe-ai/typesafe-sdk-js)). The Jev contract types mirror the SDK's type
   names: `JevRequest`, `JevChoiceQuestion`, `JevResult`, `JevChoiceResponse`, and so on.

3. The model reads the answers and writes the reply. Here it routes each support ticket and sends uncertain tickets to
   human review.
4. The same tool is answered by a local keyword classifier instead of the TypeSafe API, through `UseClient` and the
   agent's services (see [Using another client](#using-another-client)).

To use Jev as the agent's chat client instead, answering questions about the whole conversation, see
[Agent with TypeSafe](../../AgentProviders/typesafe/Agent_With_TypeSafe/).

## Configuring the client

`JevAIToolBuilder` hides the HTTP client. The API key is an `ApiKeyCredential`, and `JevAIToolOptions` follows the
`ClientPipelineOptions` pattern of the OpenAI and Azure AI client libraries:

```csharp
var options = new JevAIToolOptions
{
    ModelId = "jev-latest",                                        // default
    Transport = new HttpClientPipelineTransport(httpClient),       // for example from IHttpClientFactory
    NetworkTimeout = TimeSpan.FromSeconds(30),
};
options.AddPolicy(myPolicy, PipelinePosition.PerCall);            // custom pipeline policies

AIFunction jev = new JevAIToolBuilder(new ApiKeyCredential(apiKey), options).Build();
```

Unset pipeline settings get the defaults of the official SDK: two retries on 408, 429, and 5xx responses (529 means
overloaded), honoring `retry-after-ms` or `Retry-After` up to one minute and otherwise backing off from half a second
to five seconds, and a 10-second timeout per attempt. `Name` and `Description` set what the agent's model sees.

## Using another client

Any other client can answer the requests instead of the TypeSafe API. The second part of the sample shows it with
`KeywordClassifier`, a local classifier in [KeywordClassifier.cs](./KeywordClassifier.cs) that has its own request and
response types, knows nothing about Jev, and needs no network. `UseClient` takes the client's operation and two
mappers between the Jev types and the client's types:

```csharp
AIFunction localJev = new JevAIToolBuilder()
    .UseClient<KeywordClassifier, ClassificationRequest, ClassificationResponse>(
        (classifier, request, cancellationToken) => classifier.ClassifyAsync(request, cancellationToken),
        inputMapper: ToClassificationRequest,
        outputMapper: ToJevResult)
    .Build();
```

`ToClassificationRequest` turns each Jev question into a classifier task, and `ToJevResult` turns each classifier
result back into the Jev answer of the same kind (see the `mappers` region of [Program.cs](./Program.cs)). The tool
checks the mapped result before the model sees it: every question needs an answer of the same type, and a `choice`
answer and its probabilities may only use the labels the question offered. The output mapper receives only the
client's response, so the client's result says which kind of answer it is.

The keyword classifier is far less certain than Jev, so for the same invoice ticket the agent's confidence rule
usually sends it to human review. Use `UseMapping` instead of `UseClient` for a mapping that is a single delegate from
a `JevRequest` to a `JevResult`.

## Dependency injection

Every mapping receives the `IServiceProvider` of the agent that calls the tool. `FunctionInvokingChatClient` passes
it in `AIFunctionArguments.Services`, from the services the agent was created with. `UseClient<TClient, ...>` resolves
the client from a new scope on every call and disposes the scope afterwards, so scoped and disposable clients work
even though hosted agents are singletons that receive the root provider. The sample registers the classifier in a
`ServiceCollection` and passes the provider to the agent:

```csharp
using ServiceProvider services = new ServiceCollection()
    .AddSingleton<KeywordClassifier>()
    .BuildServiceProvider();
AIAgent localAgent = projectClient.AsAIAgent(model: deploymentName, instructions: Instructions, tools: [localJev], services: services);
```

In a host, register the client and build the tool in the agent's tool factory:

```csharp
builder.Services.AddScoped<KeywordClassifier>();
builder.Services.AddAIAgent("triage", Instructions)
    .WithAITool(sp => new JevAIToolBuilder()
        .UseClient<KeywordClassifier, ClassificationRequest, ClassificationResponse>(
            (classifier, request, cancellationToken) => classifier.ClassifyAsync(request, cancellationToken),
            inputMapper: ToClassificationRequest,
            outputMapper: ToJevResult)
        .Build());
```

With the TypeSafe API, build the tool in the same `WithAITool` factory and take the credential and the transport from
the container or configuration.

## Prerequisites

- .NET 10 SDK or later
- A Microsoft Foundry project with a model deployment
- Azure CLI installed and authenticated (for Azure credential authentication)
- A TypeSafe API key (see the [TypeSafe quickstart](https://docs.typesafe.ai/introduction/quickstart))

Set the following environment variables:

```powershell
$env:FOUNDRY_PROJECT_ENDPOINT="https://your-foundry-service.services.ai.azure.com/api/projects/your-foundry-project" # Replace with your Foundry project endpoint
$env:FOUNDRY_MODEL="gpt-5.4-mini"  # Optional, defaults to gpt-5.4-mini
$env:TYPESAFE_API_KEY="<your-api-key>"
```

## Run the sample

```powershell
cd dotnet/samples/02-agents/Agents/Agent_Step25_ClassificationWithJev
dotnet run
```
