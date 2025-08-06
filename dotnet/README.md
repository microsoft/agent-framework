# Get Started with Microsoft Agent Framework for C# Developers

## Run the Minimal Console demo

The Minimal Console demo is a simple console application which shows how to create and run an agent.

Supported Platforms:
- .Net: net9.0, net8.0, netstandard2.0, net472 
- OS: Windows, macOS, Linux

If you want to use the latest published packages following the instructions [here](../docs/FAQS.md).

### 1. Configure required environment variables

This samples used Azure OpenAI by default so you need to set the following environment variable

``` powershell
$env:AZURE_OPENAI_ENDPOINT = "https://<your deployment>.openai.azure.com/"
```

If you want to use OpenAI

1. Edit [Program.cs](./demos/MinimalConsole/Program.cs)
    ```csharp
    ```
2. Create an environment variable with your OpenAI key 
    ``` powershell
    $env:OPENAI_API_KEY = "sk-..."
    ```

### 2. Build the project

```powershell
cd demos\MinimalConsole
dotnet restore
```

### 3. Run the demonstration

``` powershell
dotnet run --framework net9.0 --no-build
```

Sample output:

```
The weather in Amsterdam is currently cloudy, with a high temperature of 15°C.
```

