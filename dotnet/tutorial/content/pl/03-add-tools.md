# Dodawanie narzędzi

**Przykład:** `dotnet/samples/01-get-started/02_add_tools/`

Narzędzia pozwalają agentowi wywoływać funkcje .NET w Twoim imieniu. Model LLM sam decyduje, kiedy i jak je wywołać, na podstawie rozmowy.

## Kompletny program

```csharp
// Copyright (c) Microsoft. All rights reserved.

using System.ComponentModel;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";

// Utwórz klienta czatu i agenta, przekazując narzędzie funkcyjne do agenta.
AIAgent agent = new OpenAIClient(apiKey)
    .GetChatClient(model)
    .AsAIAgent(instructions: "You are a helpful assistant", tools: [AIFunctionFactory.Create(GetWeather)]);

// Interakcja bez strumieniowania.
Console.WriteLine(await agent.RunAsync("What is the weather like in Amsterdam?"));

// Interakcja ze strumieniowaniem.
await foreach (var update in agent.RunStreamingAsync("What is the weather like in Amsterdam?"))
{
    Console.WriteLine(update);
}
```

## Jak działają narzędzia

Gdy przekazujesz narzędzia do agenta, przy każdym wywołaniu dzieje się co następuje:

1. MAF wysyła rozmowę + schematy narzędzi do modelu LLM
2. Model LLM decyduje się wywołać `GetWeather` z parametrem `location = "Amsterdam"`
3. `FunctionInvokingChatClient` (wbudowany w MAF) wywołuje Twoją lokalną funkcję
4. Wynik jest dołączany do rozmowy
5. Model LLM generuje ostateczną odpowiedź z użyciem danych z narzędzia

To standardowy przepływ [function calling w OpenAI](https://platform.openai.com/docs/guides/function-calling), ukryty za prostą abstrakcją.

## Definiowanie narzędzia

```csharp
[Description("Get the weather for a given location.")]
static string GetWeather([Description("The location to get the weather for.")] string location)
    => $"The weather in {location} is cloudy with a high of 15°C.";
```

Atrybuty `[Description]` na **metodzie** i **parametrach** stają się schematem JSON, na podstawie którego model LLM decyduje, kiedy i jak wywołać funkcję. Pisz jasne opisy — model je czyta.

## Rejestracja narzędzi

```csharp
.AsAIAgent(
    instructions: "You are a helpful assistant",
    tools: [AIFunctionFactory.Create(GetWeather)]
)
```

`AIFunctionFactory.Create` analizuje sygnaturę metody i atrybuty opisów, tworząc `AIFunction` z właściwym schematem. Przekazuj wiele narzędzi jako tablicę.

## Typowe wzorce narzędzi

Narzędzia nie muszą być statycznymi funkcjami-zaślepkami. Typowe wzorce:

```csharp
// Metoda instancji na serwisie
AIFunction searchTool = AIFunctionFactory.Create(searchService.SearchAsync);

// Lambda (dla prostych przypadków)
AIFunction dateTool = AIFunctionFactory.Create(
    () => DateTime.UtcNow.ToString("R"),
    name: "GetCurrentTime",
    description: "Returns the current UTC time.");

// Narzędzie asynchroniczne
[Description("Look up order status in the database.")]
static async Task<string> GetOrderStatus([Description("The order ID.")] string orderId)
{
    var order = await db.Orders.FindAsync(orderId);
    return order?.Status ?? "Not found";
}
```

## Uruchamianie przykładu

```bash
cd dotnet/samples/01-get-started/02_add_tools
dotnet run
```

## Kluczowe wnioski

- Narzędzia to metody .NET ozdobione atrybutami `[Description]`
- `AIFunctionFactory.Create` automatycznie generuje schemat JSON
- Przekazuj narzędzia przez parametr `tools:` metody `.AsAIAgent()`
- MAF obsługuje pętlę wywoływania funkcji — Ty tylko implementujesz funkcję
