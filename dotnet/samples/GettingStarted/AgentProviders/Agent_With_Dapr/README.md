# Prerequisites

Before you begin, ensure you have the following prerequisites:

- .NET 8.0 SDK or later
- Docker installed and running on your machine
- Ollama installed
- Dapr CLI installed ([instructions](https://docs.dapr.io/getting-started/install-dapr-cli/))

You'll need to download a model from [Ollama's library](https://ollama.com/library) to get started. Open
a terminal and run the following, replacing '<model_name>' with the name of the model you want to use from
Ollama's library (e.g., `llama3.2`).

```powershell
ollama run <model_name>
```

Once it has downloaded and started running, update the component bundled with this example 
in `./Components/conversation-ollama.yaml` to reflect the name of the model you just installed, modifying the value of
the `name` metadata property, then save your changes and close the file. 

Next, start your Dapr sidecar and tell it where it can look for your components. If launching from this project's directory,
run the following; otherwise, replace `./Components` with the path to your components directory.

```powershell
dapr run --app-id agents --resources-path ./Components --dapr-grpc-port 3501
```

Because the Dapr sidecar needs to continue running while your application is running, please open another terminal
window and run the following command from this project's directory to start the demo.

```powershell
dotnet run
```
