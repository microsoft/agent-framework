# Rozmowy wieloturowe

**Przykład:** `dotnet/samples/01-get-started/03_multi_turn/`

Obiekt sesji zachowuje kontekst rozmowy pomiędzy wieloma wywołaniami `RunAsync`. Agent pamięta, co zostało wcześniej powiedziane.

## Kompletny program

```csharp
// Copyright (c) Microsoft. All rights reserved.

using Microsoft.Agents.AI;
using OpenAI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(instructions: "You are good at telling jokes.", name: "Joker");

// Wywołaj agenta w rozmowie wieloturowej — kontekst jest zachowany w obiekcie sesji.
AgentSession session = await agent.CreateSessionAsync();
Console.WriteLine(await agent.RunAsync("Tell me a joke about a pirate.", session));
Console.WriteLine(await agent.RunAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session));

// Rozmowa wieloturowa ze strumieniowaniem.
session = await agent.CreateSessionAsync();
await foreach (var update in agent.RunStreamingAsync("Tell me a joke about a pirate.", session))
{
    Console.WriteLine(update);
}
await foreach (var update in agent.RunStreamingAsync("Now add some emojis to the joke and tell it in the voice of a pirate's parrot.", session))
{
    Console.WriteLine(update);
}
```

## Jak działają sesje

Bez sesji każde wywołanie `RunAsync` jest niezależne — agent nie pamięta poprzednich wiadomości.

```csharp
// Bez sesji — bezstanowe
await agent.RunAsync("Tell me a joke about a pirate.");
await agent.RunAsync("Now tell it in pirate voice."); // ← agent zapomniał żart
```

Dzięki sesji pełna historia wiadomości jest gromadzona i wysyłana przy każdym żądaniu:

```csharp
AgentSession session = await agent.CreateSessionAsync();
await agent.RunAsync("Tell me a joke about a pirate.", session);
await agent.RunAsync("Now tell it in pirate voice.", session); // ← agent pamięta żart
```

Wewnętrznie `AgentSession` gromadzi listę obiektów `ChatMessage` (wiadomości użytkownika, odpowiedzi asystenta, wywołania narzędzi i wyniki). Każde nowe wywołanie `RunAsync` dołącza do tej listy i wysyła pełną historię do modelu LLM.

## Cykl życia sesji

```csharp
// Tworzenie
AgentSession session = await agent.CreateSessionAsync();

// Użycie (wiele tur)
await agent.RunAsync("wiadomość 1", session);
await agent.RunAsync("wiadomość 2", session);

// Serializacja (do trwałego przechowywania)
JsonElement saved = await agent.SerializeSessionAsync(session);

// Deserializacja (przywróć później)
AgentSession restored = await agent.DeserializeSessionAsync(saved);
await agent.RunAsync("wiadomość 3", restored); // ← kontynuuje od miejsca, gdzie skończyliśmy
```

Serializacja sesji jest omówiona szczegółowo w rozdziale [Pamięć agenta](./05-memory).

## Kiedy używać sesji

| Scenariusz | Używać sesji? |
|---|---|
| Pojedyncze pytanie i odpowiedź | Nie |
| Aplikacja czatowa | Tak |
| Pipeline, gdzie każdy krok jest niezależny | Nie |
| Interaktywny asystent z kontekstem | Tak |
| Wsadowe przetwarzanie niezależnych elementów | Nie |

## Uruchamianie przykładu

```bash
cd dotnet/samples/01-get-started/03_multi_turn
dotnet run
```

## Kluczowe wnioski

- `agent.CreateSessionAsync()` tworzy nowy wątek rozmowy
- Przekazuj sesję do każdego wywołania `RunAsync` / `RunStreamingAsync`, aby zachować kontekst
- Sesje gromadzą pełną historię wiadomości
- Sesje serializują się do `JsonElement` w celu trwałego przechowywania i wznawiania
