# ChatKit Integration Sample with Weather Agent

This sample demonstrates how to integrate Microsoft Agent Framework with OpenAI ChatKit using a weather assistant. It shows a complete full-stack application with:

- **Backend**: FastAPI server using Agent Framework with Azure OpenAI
- **Frontend**: React + TypeScript UI using ChatKit React components
- **Features**: Weather information, current time, and a polished chat interface

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  React Frontend │ ───▶ │  FastAPI Backend │ ───▶ │  Azure OpenAI   │
│  (ChatKit UI)   │ ◀─── │ (Agent Framework)│ ◀─── │                 │
└─────────────────┘      └──────────────────┘      └─────────────────┘
```

## Prerequisites

- Python 3.10+
- Node.js 18.18+ and npm 9+
- Azure OpenAI service configured
- Azure CLI for authentication (`az login`)

## Setup

### 1. Backend Setup

Install the required Python packages:

```bash
cd python/samples/chatkit-integration
pip install agent-framework-chatkit fastapi uvicorn azure-identity
```

Set your Azure OpenAI configuration:

```bash
export AZURE_OPENAI_ENDPOINT="https://your-resource.openai.azure.com/"
export AZURE_OPENAI_API_VERSION="2024-06-01"
export AZURE_OPENAI_CHAT_DEPLOYMENT_NAME="gpt-4o"
```

Authenticate with Azure:

```bash
az login
```

### 2. Frontend Setup

Install the Node.js dependencies:

```bash
cd frontend
npm install
```

## Running the Application

### Start the Backend Server

From the `chatkit-integration` directory:

```bash
python app.py
```

The backend will start on `http://localhost:8001`

### Start the Frontend Development Server

In a new terminal, from the `frontend` directory:

```bash
npm run dev
```

The frontend will start on `http://localhost:5171`

### Access the Application

Open your browser and navigate to:

```
http://localhost:5171
```

You should see the Weather Assistant interface where you can:

- Ask about weather in any location
- Get the current time
- Use the starter prompts or type your own queries

## Features

### Backend Components

- **`app.py`**: Main FastAPI application with ChatKit integration
- **`store.py`**: SQLite-based store for ChatKit data persistence
- **Weather Agent**: Uses Agent Framework with Azure OpenAI to provide weather information

### Frontend Components

- **Modern UI**: Beautiful gradient backgrounds with dark mode support
- **ChatKit Integration**: Full-featured chat interface with streaming responses
- **Responsive Design**: Works on desktop and mobile devices
- **Theme Toggle**: Switch between light and dark modes

## Project Structure

```
chatkit-integration/
├── app.py                    # FastAPI backend with Agent Framework
├── store.py                  # SQLite store implementation
├── chatkit_demo.db          # SQLite database (auto-created)
├── README.md                 # This file
└── frontend/
    ├── package.json          # Node.js dependencies
    ├── vite.config.ts        # Vite configuration
    ├── tsconfig.json         # TypeScript configuration
    ├── tailwind.config.ts    # Tailwind CSS configuration
    ├── index.html            # HTML entry point
    └── src/
        ├── main.tsx          # React entry point
        ├── App.tsx           # Main App component
        ├── index.css         # Global styles
        ├── components/
        │   ├── Home.tsx      # Main page layout
        │   ├── ChatKitPanel.tsx    # ChatKit integration
        │   └── ThemeToggle.tsx     # Theme switcher
        ├── hooks/
        │   └── useColorScheme.ts   # Theme management
        └── lib/
            └── config.ts     # Configuration constants
```

## Configuration

### Backend Environment Variables

- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint URL
- `AZURE_OPENAI_API_VERSION`: API version (e.g., "2024-06-01")
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: Your chat model deployment name

### Frontend Environment Variables

You can customize the frontend by creating a `.env` file in the `frontend` directory:

```bash
# Optional: Custom backend URL (default: http://127.0.0.1:8001)
VITE_BACKEND_URL=http://localhost:8001

# Optional: Custom greeting message
VITE_GREETING="Welcome! Ask me about the weather!"

# Optional: ChatKit domain key (use default for local development)
VITE_CHATKIT_API_DOMAIN_KEY=domain_pk_localhost_dev
```

## Development

### Building for Production

Backend:

```bash
# The backend can be deployed using any ASGI server
uvicorn app:app --host 0.0.0.0 --port 8001
```

Frontend:

```bash
cd frontend
npm run build
```

The built files will be in `frontend/dist/` and can be served by any static file server.

## Customization

### Adding New Tools

To add new capabilities to the agent, add functions to `app.py`:

```python
def my_new_tool(param: str) -> str:
    """Tool description for the LLM."""
    # Your tool implementation
    return result

# Add to the agent
weather_agent = ChatAgent(
    chat_client=AzureOpenAIChatClient(credential=AzureCliCredential()),
    instructions="...",
    tools=[get_weather, get_time, my_new_tool],  # Add your tool here
)
```

### Styling the Frontend

The frontend uses Tailwind CSS. Modify the components in `frontend/src/components/` to change the appearance.

## Troubleshooting

### Backend Issues

- **Authentication errors**: Run `az login` and ensure you have access to the Azure OpenAI resource
- **Module not found**: Make sure all Python packages are installed
- **Port already in use**: Change the port in `app.py` and update `frontend/vite.config.ts` accordingly

### Frontend Issues

- **Dependencies not found**: Run `npm install` in the `frontend` directory
- **Cannot connect to backend**: Ensure the backend is running on port 8001
- **Build errors**: Check that Node.js version is 18.18 or higher

## Sample Conversations

Try these example queries:

- "What's the weather like in Tokyo?"
- "Tell me the weather in London and Paris"
- "What's the current time?"
- "What's the weather in Seattle and what time is it?"

## Learn More

- [Agent Framework Documentation](https://aka.ms/agent-framework)
- [ChatKit Documentation](https://platform.openai.com/docs/guides/chatkit)
- [Azure OpenAI Documentation](https://learn.microsoft.com/en-us/azure/ai-foundry/)

## License

This sample is part of the Microsoft Agent Framework project and follows the same license.
