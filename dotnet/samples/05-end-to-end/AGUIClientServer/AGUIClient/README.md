# AG-UI Client

This is a console application that demonstrates how to connect to an AG-UI server and interact with remote agents using the AG-UI protocol.

## Features

- Connects to an AG-UI server endpoint
- Displays streaming updates with color-coded output:
  - **Yellow**: Run started notifications
  - **Cyan**: Agent text responses (streamed)
  - **Green**: Run finished notifications
  - **Red**: Error messages (if any)
- Interactive prompt loop for sending messages

## Configuration

Set the following environment variable to specify the AG-UI server URL:

```powershell
$env:AGUI_SERVER_URL="http://localhost:5100"
```

If not set, the default is `http://localhost:5100`.

## Running the Client

1. Make sure the AG-UI server is running
2. Run the client:
   ```bash
   cd AGUIClient
   dotnet run
   ```
3. Enter your messages and observe the streaming updates
4. Type `:q` or `quit` to exit
