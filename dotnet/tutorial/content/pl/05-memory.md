# Pamięć agenta

**Przykład:** `dotnet/samples/01-get-started/04_memory/`

`AIContextProvider` to punkt rozszerzenia MAF dla niestandardowej pamięci. Pozwala wstrzykiwać dodatkowy kontekst przed każdym wywołaniem modelu LLM i wyodrębniać informacje po każdej odpowiedzi.

## Kompletny program

```csharp
// Copyright (c) Microsoft. All rights reserved.

using System.Text;
using System.Text.Json;
using Microsoft.Agents.AI;
using Microsoft.Extensions.AI;
using OpenAI;
using OpenAI.Chat;
using SampleApp;

var apiKey = Environment.GetEnvironmentVariable("OPENAI_API_KEY")
    ?? throw new InvalidOperationException("OPENAI_API_KEY is not set.");
var model = Environment.GetEnvironmentVariable("OPENAI_MODEL") ?? "gpt-4o-mini";

ChatClient chatClient = new OpenAIClient(apiKey)
    .GetChatClient(model);

// Utwórz agenta z niestandardowym komponentem pamięci dla każdej sesji.
AIAgent agent = chatClient.AsAIAgent(new ChatClientAgentOptions()
{
    ChatOptions = new() { Instructions = "Jesteś przyjaznym asystentem. Zawsze zwracaj się do użytkownika po imieniu." },
    AIContextProviders = [new UserInfoMemory(chatClient.AsIChatClient())]
});

AgentSession session = await agent.CreateSessionAsync();

Console.WriteLine(">> Sesja z pustą pamięcią\n");
Console.WriteLine(await agent.RunAsync("Cześć, ile wynosi pierwiastek kwadratowy z 9?", session));
Console.WriteLine(await agent.RunAsync("Mam na imię Ruaidhrí", session));
Console.WriteLine(await agent.RunAsync("Mam 20 lat", session));

// Serializuj sesję — zawiera stan pamięci.
JsonElement sessionElement = await agent.SerializeSessionAsync(session);

Console.WriteLine("\n>> Deserializowana sesja z wcześniej utworzoną pamięcią\n");
var deserializedSession = await agent.DeserializeSessionAsync(sessionElement);
Console.WriteLine(await agent.RunAsync("Jak mam na imię i ile mam lat?", deserializedSession));

Console.WriteLine("\n>> Odczyt pamięci przez komponent pamięci\n");
var userInfo = agent.GetService<UserInfoMemory>()?.GetUserInfo(deserializedSession);
Console.WriteLine($"PAMIĘĆ - Imię użytkownika: {userInfo?.UserName}");
Console.WriteLine($"PAMIĘĆ - Wiek użytkownika: {userInfo?.UserAge}");

Console.WriteLine("\n>> Nowa sesja z wcześniej utworzonymi wspomnieniami\n");
var newSession = await agent.CreateSessionAsync();
if (userInfo is not null && agent.GetService<UserInfoMemory>() is UserInfoMemory newSessionMemory)
{
    newSessionMemory.SetUserInfo(newSession, userInfo);
}
Console.WriteLine(await agent.RunAsync("Jak mam na imię i ile mam lat?", newSession));
```

## Komponent `UserInfoMemory`

```csharp
internal sealed class UserInfoMemory : AIContextProvider
{
    private readonly ProviderSessionState<UserInfo> _sessionState;
    private readonly IChatClient _chatClient;

    public UserInfoMemory(IChatClient chatClient, Func<AgentSession?, UserInfo>? stateInitializer = null)
    {
        this._sessionState = new ProviderSessionState<UserInfo>(
            stateInitializer ?? (_ => new UserInfo()),
            this.GetType().Name);
        this._chatClient = chatClient;
    }

    public override IReadOnlyList<string> StateKeys => [this._sessionState.StateKey];

    public UserInfo GetUserInfo(AgentSession session)
        => this._sessionState.GetOrInitializeState(session);

    public void SetUserInfo(AgentSession session, UserInfo userInfo)
        => this._sessionState.SaveState(session, userInfo);

    // Wywoływany PO każdej odpowiedzi modelu — wyodrębnij i zapisz informacje
    protected override async ValueTask StoreAIContextAsync(InvokedContext context, CancellationToken cancellationToken = default)
    {
        var userInfo = this._sessionState.GetOrInitializeState(context.Session);

        if ((userInfo.UserName is null || userInfo.UserAge is null)
            && context.RequestMessages.Any(x => x.Role == ChatRole.User))
        {
            var result = await this._chatClient.GetResponseAsync<UserInfo>(
                context.RequestMessages,
                new ChatOptions()
                {
                    Instructions = "Wyodrębnij imię i wiek użytkownika z wiadomości, jeśli są podane. Jeśli nie, zwróć null."
                },
                cancellationToken: cancellationToken);

            userInfo.UserName ??= result.Result.UserName;
            userInfo.UserAge ??= result.Result.UserAge;
        }

        this._sessionState.SaveState(context.Session, userInfo);
    }

    // Wywoływany PRZED każdym żądaniem do modelu — wstrzyknij kontekst do promptu
    protected override ValueTask<AIContext> ProvideAIContextAsync(InvokingContext context, CancellationToken cancellationToken = default)
    {
        var userInfo = this._sessionState.GetOrInitializeState(context.Session);
        StringBuilder instructions = new();

        instructions
            .AppendLine(userInfo.UserName is null
                ? "Zapytaj użytkownika o imię i grzecznie odmów odpowiadania na pytania, dopóki go nie poda."
                : $"Imię użytkownika to {userInfo.UserName}.")
            .AppendLine(userInfo.UserAge is null
                ? "Zapytaj użytkownika o wiek i grzecznie odmów odpowiadania na pytania, dopóki go nie poda."
                : $"Wiek użytkownika to {userInfo.UserAge}.");

        return new ValueTask<AIContext>(new AIContext { Instructions = instructions.ToString() });
    }
}

internal sealed class UserInfo
{
    public string? UserName { get; set; }
    public int? UserAge { get; set; }
}
```

## Jak działa `AIContextProvider`

Dwa haki uruchamiane przy każdym wywołaniu agenta:

```
Wiadomość użytkownika nadchodzi
       ↓
ProvideAIContextAsync()  ← wstrzyknij dodatkowe instrukcje / pobrane fakty
       ↓
Żądanie do modelu LLM wysłane
       ↓
Odpowiedź modelu LLM odebrana
       ↓
StoreAIContextAsync()    ← wyodrębnij i utrwal informacje z wymiany
       ↓
Odpowiedź zwrócona do wywołującego
```

### `ProvideAIContextAsync`

Uruchamiana przed wywołaniem modelu LLM. Zwróć `AIContext` z dodatkowymi `Instructions` do dołączenia na początku promptu systemowego. Użyj do:

- Wstrzykiwania pobranych dokumentów (RAG)
- Dodawania faktów z profilu użytkownika
- Dostarczania aktualnej daty/czasu

### `StoreAIContextAsync`

Uruchamiana po odpowiedzi modelu LLM. Użyj `context.RequestMessages`, aby sprawdzić, co zostało powiedziane. Użyj do:

- Wyodrębniania encji (imiona, daty, preferencje)
- Aktualizacji profili użytkowników
- Logowania lub audytu

## Stan z zasięgiem sesji

`ProviderSessionState<T>` przechowuje dane per-sesja wewnątrz `StateBag` sesji. Oznacza to, że stan podróżuje z sesją podczas serializacji:

```csharp
// Stan jest automatycznie uwzględniany w serializacji
JsonElement saved = await agent.SerializeSessionAsync(session);
AgentSession restored = await agent.DeserializeSessionAsync(saved);
// ← Stan UserInfoMemory jest w pełni przywrócony
```

## Przenoszenie pamięci do nowej sesji

```csharp
var newSession = await agent.CreateSessionAsync();
if (userInfo is not null && agent.GetService<UserInfoMemory>() is UserInfoMemory mem)
{
    mem.SetUserInfo(newSession, userInfo);
}
```

Pozwala to rozpocząć nową rozmowę (bez historii wiadomości), zachowując zapamiętane fakty.

## Uruchamianie przykładu

```bash
cd dotnet/samples/01-get-started/04_memory
dotnet run
```

## Kluczowe wnioski

- Utwórz podklasę `AIContextProvider`, aby zbudować niestandardową pamięć
- `ProvideAIContextAsync` — wstrzyknij kontekst przed wywołaniem modelu LLM
- `StoreAIContextAsync` — wyodrębnij stan po odpowiedzi modelu LLM
- `ProviderSessionState<T>` — przechowywanie per-sesja, które serializuje się automatycznie
- `agent.GetService<T>()` — pobierz zarejestrowany provider spoza agenta
