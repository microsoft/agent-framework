# Hello Agent

**Przykład:** `dotnet/samples/01-get-started/01_hello_agent/`

To najprostszy możliwy agent MAF: jeden plik, który tworzy agenta, prosi go o opowiedzenie żartu, a następnie robi to samo ze strumieniowaniem.

## Kompletny program

```csharp
// Copyright (c) Microsoft. All rights reserved.

// Ten przykład pokazuje, jak stworzyć i używać prostego agenta AI z Azure OpenAI jako backendem.

using Azure.AI.OpenAI;
using Azure.Identity;
using Microsoft.Agents.AI;
using OpenAI.Chat;

var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";

AIAgent agent = new AzureOpenAIClient(
    new Uri(endpoint),
    new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

// Wywołaj agenta i wyświetl wynik tekstowy.
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));

// Wywołaj agenta z obsługą strumieniowania.
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}
```

## Analiza krok po kroku

### 1. Odczyt konfiguracji ze zmiennych środowiskowych

```csharp
var endpoint = Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")
    ?? throw new InvalidOperationException("AZURE_OPENAI_ENDPOINT is not set.");
var deploymentName = Environment.GetEnvironmentVariable("AZURE_OPENAI_DEPLOYMENT_NAME") ?? "gpt-4o-mini";
```

MAF stosuje konwencję odczytywania sekretów ze zmiennych środowiskowych — nigdy na stałe w kodzie.

### 2. Budowanie agenta

```csharp
AIAgent agent = new AzureOpenAIClient(new Uri(endpoint), new DefaultAzureCredential())
    .GetChatClient(deploymentName)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");
```

Trzy wywołania w łańcuchu:

| Wywołanie | Co robi |
|---|---|
| `new AzureOpenAIClient(...)` | Tworzy połączenie z Azure OpenAI |
| `.GetChatClient(deploymentName)` | Pobiera `ChatClient` dla wskazanego wdrożenia |
| `.AsAIAgent(...)` | Opakowuje go w `ChatClientAgent` (implementuje `AIAgent`) |

Parametr `instructions` staje się promptem systemowym. Parametr `name` to metadane — przydatne przy logowaniu i przepływach wieloagentowych.

### 3. Wywołanie bez strumieniowania

```csharp
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate."));
```

`RunAsync` zbiera całą odpowiedź przed zwróceniem. Użyj tej metody, gdy potrzebujesz pełnej odpowiedzi przed kontynuowaniem.

### 4. Wywołanie ze strumieniowaniem

```csharp
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate."))
{
    Console.WriteLine(update);
}
```

`RunStreamingAsync` zwraca `IAsyncEnumerable<string>`. Każdy `update` to fragment odpowiedzi napływający na bieżąco z modelu. Użyj tej metody w interaktywnych interfejsach, gdzie chcesz wyświetlać wyniki stopniowo.

## Uruchamianie przykładu

```bash
cd dotnet/samples/01-get-started/01_hello_agent
dotnet run
```

## Kluczowe wnioski

- `AIAgent` to podstawowa abstrakcja — wszystkie agenty ją implementują
- `.AsAIAgent()` to punkt wejścia — opakuj dowolny `IChatClient`, aby uzyskać pełnego agenta
- `RunAsync` i `RunStreamingAsync` to dwa tryby wywołania
- Brak sesji = bezstanowe; każde wywołanie jest niezależne
