# ChatKit Integration Sample with Weather Agent

This sample demonstrates how to integrate Microsoft Agent Framework with OpenAI ChatKit using a weather assistant with **interactive widget visualization**. It provides a minimal full-stack application with:

- **Backend**: FastAPI server using Agent Framework with Azure OpenAI
- **Frontend**: Minimal React + TypeScript UI using ChatKit React components
- **Features**:
  - Weather information with beautiful interactive widgets
  - Current time queries
  - Chat interface with streaming responses
  - Visual weather cards with conditions, temperature, humidity, and wind

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────┐
│  React Frontend │ ───▶ │  FastAPI Backend │ ───▶ │  Azure OpenAI   │
│  (ChatKit UI)   │ ◀─── │ (Agent Framework)│ ◀─── │                 │
│                 │      │   + Widgets      │      │                 │
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

- Ask about weather in any location - **Weather widgets will be displayed automatically!**
- Get the current time
- Use the starter prompts or type your own queries
- View beautiful, interactive weather cards with icons and details

## Features

### Interactive Weather Widgets

When you ask about weather, the assistant displays a beautiful interactive card showing:

- **Location and weather condition**
- **Temperature** with a visual icon (sunny, cloudy, rainy, stormy, snowy, foggy)
- **Weather details**: Humidity percentage and wind speed
- **Clean, modern design** following ChatKit widget guidelines

The widgets are created using ChatKit's widget system and are displayed alongside the text response.

### City Selector Widget

Ask the assistant to show you cities or list available locations, and it will display an interactive city selector widget featuring:

- **Clickable city buttons**: Each city is a button that automatically asks for its weather
- **One-click weather**: Simply click a city name to get instant weather information
- **Popular locations**: 10 major US cities organized in an easy-to-browse grid
- **Regional coverage**: Cities from Pacific Northwest, East Coast, Bay Area, and more
- **Flexible input**: Users can still type to ask about any city worldwide

Simply say "show me cities" or "what cities can I choose from?" to see the selector, then click any city!

### Backend Components

- **`app.py`**: Main FastAPI application with ChatKit integration and widget support
- **`weather_widget.py`**: Weather and city selector widget rendering with SVG icons and ChatKit components
  - `render_weather_widget()`: Creates weather display cards
  - `render_city_selector_widget()`: Creates city selection interface
- **`store.py`**: SQLite-based store for ChatKit data persistence
- **Weather Agent**: Uses Agent Framework with Azure OpenAI to provide weather information

### Frontend Components

- **Minimal UI**: Simple, clean interface focused on ChatKit integration
- **ChatKit Integration**: Full-featured chat interface with streaming responses and widget support
- **No Complex Dependencies**: Only React and ChatKit - no styling frameworks or extra libraries

## How Widget Integration Works

This sample demonstrates the full flow of creating interactive ChatKit widgets from Agent Framework:

### Weather Widget Flow

1. **User asks a question** (e.g., "What's the weather in Seattle?")
2. **Agent Framework agent** processes the request using Azure OpenAI
3. **Tool is invoked**: The `get_weather()` function is called with the location
4. **Data is collected**: Weather data (condition, temperature, humidity, wind) is stored
5. **Text response streams**: The agent provides a text description
6. **Widget is created**: After the text response, a ChatKit widget is rendered using:
   - `render_weather_widget()`: Creates the widget structure with ChatKit components
   - SVG icons for weather conditions
   - Structured layout using Box, Card, Row, Col components
7. **Widget streams to frontend**: Using `stream_widget()` from agent_framework_chatkit

### City Selector Widget Flow

1. **User requests city list** (e.g., "show me available cities" or "what cities can I choose from?")
2. **Agent invokes tool**: The `show_city_selector()` function sets a flag
3. **Text response**: Agent confirms it will show the cities
4. **Widget is created**: After the text response, the city selector widget is rendered with clickable buttons
5. **Widget displays**: Shows a grid of clickable city buttons
6. **User clicks a city**: The button automatically sends a message "What's the weather in [City]?"
7. **Agent responds**: Processes the weather request and shows the weather widget

The buttons use ChatKit's `ActionConfig` with type `add_user_message` to automatically submit the weather query when clicked. 7. **ChatKit UI displays**: The interactive widget appears alongside the text

### Key Files for Widget Integration

```python
# weather_widget.py - Widget rendering
from chatkit.widgets import Card, Box, Row, Col, Text, Title, Image

def render_weather_widget(data: WeatherData) -> WidgetRoot:
    # Creates a Card widget with weather information
    return Card(key="weather", padding=0, children=[...])

# app.py - Integration with agent
from agent_framework_chatkit import stream_widget

# After agent response, create and stream widget
widget = render_weather_widget(weather_data)
async for event in stream_widget(thread_id=thread.id, widget=widget):
    yield event
```

The `agent_framework_chatkit` package provides the `stream_widget()` helper that:

- Creates a `WidgetItem` with the provided widget
- Wraps it in a `ThreadItemDoneEvent`
- Yields it as a ChatKit stream event

This approach keeps the widget logic separate from the agent logic while maintaining clean integration.

## Project Structure

```
chatkit-integration/
├── app.py                    # FastAPI backend with Agent Framework
├── store.py                  # SQLite store implementation
├── chatkit_demo.db          # SQLite database (auto-created)
├── README.md                 # This file
└── frontend/
    ├── package.json          # Node.js dependencies (minimal)
    ├── vite.config.ts        # Vite configuration
    ├── tsconfig.json         # TypeScript configuration
    ├── index.html            # HTML entry point with inline styles
    ├── README.md             # Frontend-specific documentation
    └── src/
        ├── main.tsx          # React entry point
        ├── App.tsx           # Main App component (ChatKit integration)
        └── vite-env.d.ts     # Vite type definitions
```

## Configuration

### Backend Environment Variables

- `AZURE_OPENAI_ENDPOINT`: Your Azure OpenAI endpoint URL
- `AZURE_OPENAI_API_VERSION`: API version (e.g., "2024-06-01")
- `AZURE_OPENAI_CHAT_DEPLOYMENT_NAME`: Your chat model deployment name

### Frontend Environment Variables

You can customize the frontend by creating a `.env` file in the `frontend` directory:

```bash
# Optional: ChatKit domain key (use default for local development)
VITE_CHATKIT_API_DOMAIN_KEY=domain_pk_localhost_dev
```

The backend URL is configured in `frontend/vite.config.ts` and defaults to `http://127.0.0.1:8001`.

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

The frontend is intentionally minimal with inline styles in `index.html`. To customize:

- **Basic styling**: Edit the `<style>` section in `index.html`
- **ChatKit appearance**: Modify the theme configuration in `src/App.tsx` (see [ChatKit theming docs](https://platform.openai.com/docs/guides/chatkit))
- **Add components**: Create new React components in a `src/components/` directory

See `frontend/README.md` for more details on customizing the frontend.

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
