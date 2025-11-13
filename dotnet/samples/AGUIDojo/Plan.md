# AG-UI Blazor Dojo - Implementation Plan

## Executive Summary

This document outlines the plan to transform the AGUIDojoClient from a simple chat application into a comprehensive AG-UI Dojo - a simplified Blazor version of [dojo.ag-ui.com/microsoft-agent-framework-dotnet](https://dojo.ag-ui.com/microsoft-agent-framework-dotnet). The dojo will showcase various AG-UI scenarios and features through an interactive demonstration platform.

## Current State Analysis

### Existing Components

**AGUIDojoServer** provides seven AG-UI endpoints:
1. `/agentic_chat` - Basic chat with frontend tools
2. `/backend_tool_rendering` - Backend tool demonstrations
3. `/human_in_the_loop` - Human approval workflows
4. `/tool_based_generative_ui` - Tool-based generative UI
5. `/agentic_generative_ui` - Agentic generative UI
6. `/shared_state` - Shared state management
7. `/predictive_state_updates` - Predictive state updates

**AGUIDojoClient** currently has:
- Basic chat interface components (Chat.razor, ChatInput.razor, ChatMessageList.razor, etc.)
- Layout components (MainLayout.razor)
- AG-UI client integration via `AGUIChatClient`

## Target Architecture

### Dojo Website Structure (from analysis)

The dojo website has the following structure:
- **Left Sidebar**: Lists all available demo scenarios with descriptions and tags
- **Main Content Area**: Contains three tabs
  - **Preview Tab**: Interactive demo of the selected scenario
  - **Code Tab**: Shows relevant code files for the scenario
  - **Docs Tab**: Documentation for the scenario
- **No Integration Selector**: We'll skip the integration dropdown since we're focused on Microsoft Agent Framework (.NET)

### Demo Scenarios

Based on the dojo website analysis, we need to support these scenarios:

1. **Agentic Chat**
   - Description: Chat with your Copilot and call frontend tools
   - Tags: Chat, Tools, Streaming
   - Endpoint: `/agentic_chat`

2. **Backend Tool Rendering**
   - Description: Render and stream your backend tools to the frontend
   - Tags: Agent State, Collaborating
   - Endpoint: `/backend_tool_rendering`

3. **Human in the Loop**
   - Description: Plan a task together and direct the Copilot to take the right steps
   - Tags: HITL, Interactivity
   - Endpoint: `/human_in_the_loop`

4. **Agentic Generative UI**
   - Description: Assign a long running task to your Copilot and see how it performs!
   - Tags: Generative UI (agent), Long running task
   - Endpoint: `/agentic_generative_ui`

5. **Tool Based Generative UI**
   - Description: Haiku generator that uses tool based generative UI
   - Tags: Generative UI (action), Tools
   - Endpoint: `/tool_based_generative_ui`

6. **Shared State between Agent and UI**
   - Description: A recipe Copilot which reads and updates collaboratively
   - Tags: Agent State, Collaborating
   - Endpoint: `/shared_state`

7. **Predictive State Updates**
   - Description: Use collaboration to edit a document in real time with your Copilot
   - Tags: State, Streaming, Tools
   - Endpoint: `/predictive_state_updates`

## Implementation Plan

### Phase 1: Project Structure & Routing

#### 1.1 Create New Component Structure

```
Components/
  Layout/
    MainLayout.razor          (Update existing)
    DemoSidebar.razor         (New - left sidebar with demo list)
    DemoViewTabs.razor        (New - Preview/Code/Docs tabs)
  
  Pages/
    Index.razor               (New - redirects to first demo)
    Demo.razor                (New - main demo container with routing)
    
  Demos/
    AgenticChat/
      AgenticChatDemo.razor   (Chat UI for this scenario)
    BackendToolRendering/
      BackendToolRenderingDemo.razor
    HumanInLoop/
      HumanInLoopDemo.razor
    AgenticGenerativeUI/
      AgenticGenerativeUIDemo.razor
    ToolBasedGenerativeUI/
      ToolBasedGenerativeUIDemo.razor
    SharedState/
      SharedStateDemo.razor
    PredictiveStateUpdates/
      PredictiveStateUpdatesDemo.razor
      
  Shared/
    DemoScenario.cs           (Model for demo metadata)
    DemoService.cs            (Service to manage demo scenarios)
    Chat/                     (Move existing chat components here)
      ChatHeader.razor
      ChatInput.razor
      ChatMessageList.razor
      ChatMessageItem.razor
      ChatSuggestions.razor
      ChatCitation.razor
```

#### 1.2 Update Routing

- Use Blazor's `@page` directive with route parameters: `@page "/microsoft-agent-framework/feature/{scenarioId}"`
- Default route `/` redirects to first scenario
- Each scenario accessible via `/microsoft-agent-framework/feature/agentic_chat`, `/microsoft-agent-framework/feature/backend_tool_rendering`, etc.
- Scenario IDs use underscores to match server endpoints and dojo convention

### Phase 2: Core Components

#### 2.1 DemoSidebar Component

**Purpose**: Display list of demo scenarios in left sidebar

**Features**:
- List all available scenarios
- Show title, description, and tags for each scenario
- Highlight currently selected scenario
- Navigate to scenario on click
- Responsive design (collapsible on mobile)

**Data Structure**:
```csharp
public record DemoScenario(
    string Id,                    // e.g., "agentic_chat", "backend_tool_rendering"
    string Title,
    string Description,
    string[] Tags,
    string Endpoint,              // e.g., "/agentic_chat"
    string Icon = "💬"
);
```

#### 2.2 DemoViewTabs Component

**Purpose**: Tab control for Preview/Code/Docs views

**Features**:
- Three tabs: Preview, Code, Docs
- Smooth tab transitions
- State persistence (current tab stays active when switching demos)
- Blazor Interactive Server rendering for tab switching

**Implementation Approach**:
- Use Blazor's `@rendermode InteractiveServer` for tab interactivity
- Tab state managed via component parameter
- CSS for tab styling similar to dojo website

#### 2.3 Demo.razor (Main Container)

**Purpose**: Container page that hosts the demo experience

**Features**:
- Route parameter for scenario selection: `@page "/microsoft-agent-framework/feature/{scenarioId}"`
- Loads appropriate demo component based on scenarioId
- Manages tab state
- Dynamically loads code/docs content

**Structure**:
```razor
@page "/microsoft-agent-framework/feature/{scenarioId}"
@rendermode InteractiveServer

<div class="dojo-container">
    <DemoSidebar CurrentScenarioId="@ScenarioId" />
    <div class="dojo-main">
        <DemoViewTabs CurrentTab="@currentTab" OnTabChanged="@OnTabChanged">
            <PreviewContent>
                @RenderScenarioDemo()
            </PreviewContent>
            <CodeContent>
                <CodeViewer Files="@GetCodeFiles()" />
            </CodeContent>
            <DocsContent>
                <DocsViewer Content="@GetDocsContent()" />
            </DocsContent>
        </DemoViewTabs>
    </div>
</div>
```

### Phase 3: Demo Scenario Components

#### 3.1 Base Pattern for Demo Components

Each demo component should:
- Accept configuration (endpoint URL, server URL)
- Use existing chat components where applicable
- Implement scenario-specific features
- Handle AG-UI client connection
- Display scenario-specific UI elements

#### 3.2 Reusable Chat Components

Move existing chat components to `Components/Shared/Chat/`:
- `ChatHeader.razor` - Header with new chat button
- `ChatInput.razor` - Message input with send button
- `ChatMessageList.razor` - Message display container
- `ChatMessageItem.razor` - Individual message rendering
- `ChatSuggestions.razor` - Suggested prompts
- `ChatCitation.razor` - Citation display

#### 3.3 Scenario-Specific Components

**AgenticChat**: Can largely reuse existing Chat.razor
- Configure to use `/agentic_chat` endpoint
- Add example prompts specific to frontend tools

**BackendToolRendering**: Similar to AgenticChat
- Configure to use `/backend_tool_rendering` endpoint
- Display backend tool execution results
- Show tool rendering in UI

**HumanInLoop**: Add approval UI
- Configure to use `/human_in_the_loop` endpoint
- Display approval requests
- Add approve/reject buttons
- Show approval workflow state

**AgenticGenerativeUI**: 
- Configure to use `/agentic_generative_ui` endpoint
- Display agent's plan/steps
- Show generative UI components
- Render dynamic UI elements

**ToolBasedGenerativeUI**:
- Configure to use `/tool_based_generative_ui` endpoint
- Haiku-specific UI
- Display generated UI components

**SharedState**:
- Configure to use `/shared_state` endpoint
- Display recipe state
- Show collaborative state updates
- Render ingredient lists, recipe steps

**PredictiveStateUpdates**:
- Configure to use `/predictive_state_updates` endpoint
- Document editing UI
- Real-time state synchronization display
- Show predictive updates as they occur

### Phase 4: Code & Documentation Views

#### 4.1 Code Viewer Component

**Purpose**: Display code files for each scenario

**Features**:
- File selector (tabs or dropdown for multiple files)
- Syntax highlighting (use a Blazor-compatible syntax highlighter)
- Copy to clipboard button
- Line numbers
- Responsive design

**Code Files per Scenario**:
- Server-side C# files from AGUIDojoServer
- Client-side Razor files
- Shared models/types

**Implementation Options**:
- Embed code as string resources
- Load from embedded resources
- Use `@@preservewhitespace` directive
- Consider using BlazorMonaco or similar for code display

#### 4.2 Docs Viewer Component

**Purpose**: Display documentation for each scenario

**Features**:
- Markdown rendering (use Markdig or similar)
- Links to external documentation
- Responsive design
- Code examples within docs

**Documentation Content**:
- Overview of the scenario
- Key concepts
- How to use the demo
- Links to related documentation
- Common patterns and best practices

### Phase 5: Styling & UX

#### 5.1 Layout & Design

**Sidebar**:
- Fixed width (e.g., 300px) on desktop
- Collapsible on mobile
- Scrollable list of demos
- Visual hierarchy with tags

**Main Content Area**:
- Fluid width
- Tabs at the top
- Full-height content area
- Proper spacing and padding

**Colors & Theme**:
- Professional color scheme
- Clear visual hierarchy
- Accessible contrast ratios
- Consistent with Microsoft design language

#### 5.2 Responsive Design

- Desktop (>1024px): Full sidebar + content
- Tablet (768px-1024px): Collapsible sidebar
- Mobile (<768px): Hamburger menu for sidebar, full-width content

#### 5.3 Loading States

- Skeleton loaders for chat messages
- Loading indicators for responses
- Smooth transitions
- Error states with retry options

### Phase 6: Configuration & State Management

#### 6.1 Demo Configuration Service

```csharp
public class DemoService
{
    private readonly IConfiguration _configuration;
    private readonly string _serverUrl;
    
    public DemoService(IConfiguration configuration)
    {
        _configuration = configuration;
        _serverUrl = configuration["SERVER_URL"] ?? "http://localhost:5100";
    }
    
    public IEnumerable<DemoScenario> GetAllScenarios() { ... }
    
    public DemoScenario? GetScenario(string id) { ... }
    
    public IChatClient CreateChatClient(string endpoint)
    {
        var httpClient = new HttpClient { BaseAddress = new Uri(_serverUrl) };
        return new AGUIChatClient(httpClient, endpoint);
    }
}
```

#### 6.2 State Management

- Use Blazor's built-in state management
- Component-level state for each demo
- Service-level state for app-wide settings
- No global state persistence needed (demos are ephemeral)

### Phase 7: Testing & Refinement

#### 7.1 Manual Testing Checklist

- [ ] All scenarios load and display correctly
- [ ] Routing works for all scenarios
- [ ] Tab switching works smoothly
- [ ] Chat functionality works in each scenario
- [ ] Code viewer displays code correctly
- [ ] Docs viewer renders markdown correctly
- [ ] Responsive design works on different screen sizes
- [ ] Error handling works properly
- [ ] Loading states display correctly

#### 7.2 Performance Considerations

- Lazy load demo components
- Minimize initial bundle size
- Use Blazor InteractiveServer for UI interactions
- Optimize chat message rendering
- Consider virtualization for long message lists

## Technical Considerations

### Blazor Render Modes

We'll use **Interactive Server** render mode (`@rendermode InteractiveServer`) for:
- Tab switching
- Demo sidebar interactions
- Chat interactions
- Real-time updates

This provides:
- Real-time updates over SignalR
- Server-side state management
- No need for WebAssembly
- Simplified deployment

### AG-UI Client Integration

Each demo component will:
1. Inject or create an `IChatClient` instance
2. Configure with the appropriate endpoint
3. Use `ChatClient.GetStreamingResponseAsync()` for streaming
4. Handle different content types (text, state, approvals, etc.)
5. Dispose properly on component disposal

### Code Organization Best Practices

Following existing conventions:
- Copyright headers on all `.cs` files
- XML documentation for public classes/methods
- Use `@inject` for dependency injection
- Use `@implements IDisposable` for cleanup
- Use `@code` blocks for component logic
- Follow Blazor naming conventions (PascalCase for components)

## Success Criteria

1. **Functional**: All seven scenarios work correctly
2. **Usable**: Intuitive navigation between scenarios and tabs
3. **Educational**: Code and docs help users understand AG-UI
4. **Performant**: Smooth interactions, fast loading
5. **Maintainable**: Clean code, good structure, easy to extend
6. **Responsive**: Works on desktop, tablet, and mobile

## Future Enhancements (Out of Scope)

- Authentication/authorization
- Saving/sharing demo sessions
- Custom scenario creation
- Integration selector (supporting multiple frameworks)
- Deployment to Azure
- Analytics/telemetry
- Dark mode toggle
- Internationalization

## Dependencies & Prerequisites

### Required NuGet Packages
- Microsoft.Agents.AI.AGUI (already referenced)
- Markdig (for markdown rendering in docs)
- BlazorMonaco or similar (optional, for code syntax highlighting)

### Environment Configuration
- Server must be running on configured port (default: 5100)
- All seven endpoints must be available on AGUIDojoServer
- Azure OpenAI credentials configured in AGUIDojoServer

## Implementation Timeline

### Phase 1 (Structure): 2-3 hours
- Create component structure
- Set up routing
- Create demo service

### Phase 2 (Core Components): 3-4 hours
- Build DemoSidebar
- Build DemoViewTabs
- Build Demo.razor container

### Phase 3 (Scenarios): 4-6 hours
- Implement all seven scenario components
- Reuse/adapt existing chat components

### Phase 4 (Code/Docs): 2-3 hours
- Build code viewer
- Build docs viewer
- Create documentation content

### Phase 5 (Styling): 2-3 hours
- Implement responsive layout
- Style components
- Add loading states

### Phase 6 (Testing): 2-3 hours
- Manual testing
- Bug fixes
- Refinements

**Total Estimated Time**: 15-22 hours

## Conclusion

This plan provides a comprehensive roadmap for building a simplified Blazor version of the AG-UI dojo. By following this plan, we'll create an educational and interactive platform that showcases the capabilities of the Microsoft Agent Framework's AG-UI integration. The modular structure ensures maintainability and extensibility for future enhancements.
