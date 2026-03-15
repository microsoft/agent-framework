# Architektura — dogłębna analiza

MAF opiera się na niewielkim zestawie podstawowych abstrakcji, które dobrze się komponują.

## Hierarchia typów

```
AIAgent  (abstrakcyjny)
└── ChatClientAgent  (konkretna implementacja)
        │
        └── używa IChatClient  (z Microsoft.Extensions.AI)
                └── AzureOpenAIChatClient, OpenAIChatClient, …
```

### `AIAgent`

Abstrakcyjna klasa bazowa, po której dziedziczą wszystkie agenty. Udostępnia:

```csharp
// Wywołanie — zwraca pełną odpowiedź jako string
Task<string> RunAsync(string message, AgentSession? session = null);
Task<string> RunAsync(ChatMessage message, AgentSession? session = null);

// Strumieniowanie — zwraca fragmenty odpowiedzi w miarę ich napływania
IAsyncEnumerable<string> RunStreamingAsync(string message, AgentSession? session = null);

// Zarządzanie sesją
Task<AgentSession> CreateSessionAsync();
Task<JsonElement> SerializeSessionAsync(AgentSession session);
Task<AgentSession> DeserializeSessionAsync(JsonElement state);

// Wyszukiwanie usług (wstrzykiwanie zależności wewnątrz agenta)
T? GetService<T>();
```

Agenty przechowują również metadane: `Id`, `Name` i `Description`.

### `AgentSession`

Reprezentuje pojedynczy wątek rozmowy. Sesje:

- Przechowują historię wiadomości wysyłanych do modelu LLM
- Zawierają `StateBag` — dowolne, serializowalne pary klucz-wartość
- Są serializowalne do/z `JsonElement` w celu trwałego przechowywania

Obiekty sesji są przekazywane do każdego wywołania `RunAsync` / `RunStreamingAsync`, aby zachować kontekst.

### `ChatClientAgent`

Wbudowana implementacja `AIAgent`. Opakowuje dowolny `IChatClient` (interfejs z `Microsoft.Extensions.AI`) i dodaje:

- Wstrzykiwanie instrukcji systemowych
- Rejestrację narzędzi/funkcji
- Potok `AIContextProvider`

Nigdy nie tworzymy `ChatClientAgent` bezpośrednio — metoda rozszerzająca `.AsAIAgent()` tworzy go automatycznie.

### `AITool` i `AIFunction`

Narzędzia to rzeczy, które agent może wywoływać. `AIFunction` jest najczęściej stosowany — opakowuje delegat .NET:

```csharp
AIFunction tool = AIFunctionFactory.Create(MojaMetoda);
```

`AIFunctionFactory.Create` używa refleksji do odczytu atrybutów `[Description]` i generowania schematu JSON potrzebnego modelowi LLM do wywołania funkcji.

### `AIContextProvider`

Hak uruchamiany przed i po każdym wywołaniu agenta:

```csharp
public abstract class AIContextProvider
{
    // Wywoływany przed żądaniem do modelu — dodaj dodatkowe instrukcje/kontekst
    protected abstract ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, ...);

    // Wywoływany po odpowiedzi modelu — wyodrębnij i zapisz informacje
    protected abstract ValueTask StoreAIContextAsync(InvokedContext context, ...);
}
```

Utwórz podklasę, aby zbudować niestandardową pamięć, wstrzykiwanie profilu użytkownika, RAG (Retrieval-Augmented Generation) itp.

## Struktura pakietów

| Pakiet | Zawartość |
|---|---|
| `Microsoft.Agents.AI` | `AIAgent`, `AgentSession`, `ChatClientAgent`, metody rozszerzające |
| `Microsoft.Agents.AI.Abstractions` | Interfejsy i abstrakcyjne klasy bazowe |
| `Microsoft.Agents.AI.Workflows` | `WorkflowBuilder`, `Executor`, `Run` |
| `Microsoft.Agents.AI.Hosting.AzureFunctions` | `ConfigureDurableAgents` |

## Zewnętrzne zależności

MAF w dużym stopniu opiera się na **`Microsoft.Extensions.AI`** — standardowej abstrakcji .NET dla usług AI:

- `IChatClient` — uniwersalny interfejs dla dostawców modeli LLM
- `ChatMessage` / `AIContent` — typy wiadomości
- `FunctionInvokingChatClient` — middleware obsługujący pętlę wywoływania funkcji

Oznacza to, że każdy dostawca dostarczający implementację `IChatClient` działa z MAF bez zmian w kodzie.

## Zasady projektowe

Plik AGENTS.md w repozytorium określa cztery zasady przewodnie:

1. **DRY** — wspólna logika trafia do helperów, nie jest powielana
2. **Pojedyncza odpowiedzialność** — każda klasa robi jedną rzecz
3. **Enkapsulacja** — szczegóły implementacji pozostają prywatne
4. **Silne typowanie** — typy dokumentują intencje i wychwytują błędy w czasie kompilacji
