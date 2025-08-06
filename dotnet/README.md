# Get Started with Microsoft Agent Framework for C# Developers

## Run the Minimal Console demo

The Minimal Console demo is a simple console application which shows how to create and run an agent.

Supported Platforms:
- .Net: net9.0, net8.0, netstandard2.0, net472 
- OS: Windows, macOS, Linux

If you want to use the latest published packages following the instructions [here](../docs/FAQS.md).

### 1. Configure required environment variables

This samples uses Azure OpenAI by default so you need to set the following environment variable

``` powershell
$env:AZURE_OPENAI_ENDPOINT = "https://<your deployment>.openai.azure.com/"
```

If you want to use OpenAI

1. Edit [Program.cs](./demos/MinimalConsole/Program.cs) and change the following lines:
    ```csharp
    AIAgent agent = new AzureOpenAIClient(
      new Uri(Environment.GetEnvironmentVariable("AZURE_OPENAI_ENDPOINT")!),
      new AzureCliCredential())
       .GetChatClient("gpt-4o-mini")
       .CreateAIAgent(
         instructions: "You are a helpful assistant, you can help the user with weather information.",
         tools: [AIFunctionFactory.Create(GetWeather)]);
    ```
    To this:
    ```csharp
    AIAgent agent = new OpenAIClient(Environment.GetEnvironmentVariable("OPENAI_API_KEY")!)
      .GetChatClient("gpt-4o-mini")
      .CreateAIAgent(
        instructions: "You are a helpful assistant, you can help the user with weather information.",
        tools: [AIFunctionFactory.Create(GetWeather)]);
    ```
2. Create an environment variable with your OpenAI key 
    ``` powershell
    $env:OPENAI_API_KEY = "sk-..."
    ```

### 2. Build the project

```powershell
cd demos\MinimalConsole
dotnet build
```

### 3. Run the demonstration

``` powershell
dotnet run --framework net9.0 --no-build
```

Sample output:

```
The weather in Amsterdam is currently cloudy, with a high temperature of 15°C.
```

