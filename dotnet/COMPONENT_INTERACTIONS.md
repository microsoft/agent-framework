# Microsoft Agent Framework - Component Interaction Diagrams

## Overview
This document provides detailed component interaction diagrams for the Microsoft Agent Framework (.NET). These diagrams use ASCII art for maximum compatibility and are viewable in any text editor.

---

## 1. Basic Agent Execution - Component Interaction

**Flow:** Application → Builder → Agent → Provider → External LLM

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     BASIC AGENT EXECUTION FLOW                          │
└─────────────────────────────────────────────────────────────────────────┘

Step 1: Configure Agent
┌──────────────────┐
│   Application    │
│                  │
└────────┬─────────┘
         │
         │ (1) Create & Configure
         ▼
┌──────────────────┐         Configuration:
│  AIAgentBuilder  │         • Set instructions
│                  │         • Add tools
│  .CreateAIAgent  │         • Set model options
│  .WithInstructions         • Add middleware
│  .WithTools()    │
│  .Build()        │
└────────┬─────────┘
         │
         │ (2) Build
         ▼

Step 2: Create Agent Instance
┌──────────────────────────────┐
│        AIAgent               │
│  (Wrapped with decorators)   │
│                              │
│  ┌────────────────────────┐  │
│  │ OpenTelemetry Wrapper  │  │
│  │  ┌──────────────────┐  │  │
│  │  │ Function Handler │  │  │
│  │  │  ┌────────────┐  │  │  │
│  │  │  │ Core Agent │  │  │  │
│  │  │  └────────────┘  │  │  │
│  │  └──────────────────┘  │  │
│  └────────────────────────┘  │
└──────────┬───────────────────┘
           │
           │ (3) RunAsync(message)
           ▼

Step 3: Execute Request
┌──────────────────────────────┐
│   Provider Implementation    │
│                              │
│  ┌─────────┐  ┌──────────┐  │
│  │ OpenAI  │  │ AzureAI  │  │
│  └─────────┘  └──────────┘  │
│  ┌─────────┐  ┌──────────┐  │
│  │  A2A    │  │ Copilot  │  │
│  └─────────┘  └──────────┘  │
└──────────┬───────────────────┘
           │
           │ (4) HTTP/API Call
           ▼
┌──────────────────────────────┐
│     External LLM API         │
│                              │
│  • OpenAI GPT-4             │
│  • Azure OpenAI             │
│  • Copilot Studio           │
│  • Other LLM services       │
└──────────┬───────────────────┘
           │
           │ (5) Response
           ▼
┌──────────────────────────────┐
│   Process Response           │
│                              │
│  • Parse JSON                │
│  • Handle tool calls         │
│  • Format messages           │
│  • Extract metadata          │
└──────────┬───────────────────┘
           │
           │ (6) Return AgentRunResponse
           ▼
┌──────────────────────────────┐
│   Application                │
│                              │
│  • Display messages          │
│  • Handle tool results       │
│  • Update UI                 │
└──────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════
TIMING DIAGRAM (Left to Right)
═══════════════════════════════════════════════════════════════════════════

App       Builder    Agent     Provider    LLM        Response
 │           │          │          │         │            │
 ├──config──>│          │          │         │            │
 │           ├─build───>│          │         │            │
 │<──────────┴──────────┤          │         │            │
 │                      │          │         │            │
 ├─────RunAsync────────>│          │         │            │
 │                      ├─execute─>│         │            │
 │                      │          ├─API────>│            │
 │                      │          │         ├─process───>│
 │                      │          │<────────┴────────────┤
 │                      │<─────────┤                      │
 │<─────────────────────┤                                 │
 │                                                         │
 └─────────────────────────────────────────────────────────┘
```

---

## 2. Workflow Execution - Component Interaction

**Flow:** Application → WorkflowBuilder → Workflow → Runner → Executors → Agents

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    WORKFLOW EXECUTION FLOW                              │
└─────────────────────────────────────────────────────────────────────────┘

Step 1: Define Workflow
┌──────────────────┐
│   Application    │
└────────┬─────────┘
         │
         │ (1) Define workflow
         ▼
┌────────────────────────┐     • Add executors (nodes)
│  WorkflowBuilder       │     • Define edges (transitions)
│                        │     • Set routing logic
│  .AddExecutor()        │     • Configure entry/exit points
│  .AddEdge()            │
│  .SetRouting()         │
│  .Build()              │
└────────┬───────────────┘
         │
         │ (2) Build
         ▼
┌────────────────────────┐
│     Workflow           │
│  (Graph Structure)     │
│                        │
│   Entry → Exec1 → Exec2 → Exit
│              ↓     ↑   │
│              → Exec3 ─┘ │
└────────┬───────────────┘
         │
         │ (3) RunAsync(input)
         ▼

Step 2: Initialize Execution
┌────────────────────────────────────┐
│      InProcessRunner               │
│  (Execution Engine)                │
└────────┬───────────────────────────┘
         │
         │ (4) Initialize
         ▼
┌────────────────────────────────────┐
│      State Manager                 │
│                                    │
│  • Current executor                │
│  • Message history                 │
│  • Execution context               │
│  • Checkpoint data                 │
└────────────────────────────────────┘

Step 3: Execute Graph (Loop)
╔════════════════════════════════════════════════════════════════╗
║                  GRAPH EXECUTION LOOP                          ║
╚════════════════════════════════════════════════════════════════╝

┌─────────────────┐
│  Executor 1     │  ◄─── Current Node
│  (Researcher)   │
└────────┬────────┘
         │
         │ Execute
         ▼
    ┌────────────────┐
    │  AIAgent       │  ◄─── If agent executor
    │  RunAsync()    │
    └────────┬───────┘
             │
             │ Response
             ▼
    ┌────────────────────┐
    │  Update State      │  ◄─── Save results
    │  • Add messages    │
    │  • Update context  │
    └────────┬───────────┘
             │
             │ Output
             ▼
    ┌──────────────────────┐
    │  Evaluate Edges      │  ◄─── Routing logic
    │  • Check conditions  │
    │  • Select next node  │
    └────────┬─────────────┘
             │
             │ Route to next
             ▼
┌─────────────────┐
│  Executor 2     │  ◄─── Next Node
│  (Writer)       │
└────────┬────────┘
         │
         │ (Repeat process)
         ▼
    [Continue until exit condition]

Step 4: Stream Results
┌────────────────────────────────────┐
│      StreamingRun                  │
│                                    │
│  ┌──────────────────────────────┐ │
│  │  Event Stream                │ │
│  │  ├─ ExecutorStarted          │ │
│  │  ├─ MessageGenerated         │ │
│  │  ├─ StateUpdated             │ │
│  │  ├─ ExecutorCompleted        │ │
│  │  └─ WorkflowCompleted        │ │
│  └──────────────────────────────┘ │
└────────┬───────────────────────────┘
         │
         │ (5) Stream events
         ▼
┌────────────────────────────────────┐
│      Application                   │
│                                    │
│  await foreach(event in run)      │
│  {                                 │
│     // Process each event          │
│  }                                 │
└────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════
PARALLEL EXECUTION EXAMPLE
═══════════════════════════════════════════════════════════════════════════

                    ┌─────────────┐
                    │   Entry     │
                    └──────┬──────┘
                           │
              ┌────────────┼────────────┐
              │            │            │
              ▼            ▼            ▼
        ┌──────────┐ ┌──────────┐ ┌──────────┐
        │ Exec A   │ │ Exec B   │ │ Exec C   │  ◄─── Parallel
        └────┬─────┘ └────┬─────┘ └────┬─────┘
             │            │            │
             └────────────┼────────────┘
                          │
                          ▼
                    ┌──────────┐
                    │   Sync   │  ◄─── Wait for all
                    └────┬─────┘
                         │
                         ▼
                    ┌──────────┐
                    │ Exec D   │  ◄─── Continue
                    └──────────┘
```

---

## 3. Declarative Workflow (YAML-Based) - Component Interaction

**Flow:** YAML File → Parser → Object Model → Builder → Executable Workflow

```
┌─────────────────────────────────────────────────────────────────────────┐
│                DECLARATIVE WORKFLOW (YAML) FLOW                         │
└─────────────────────────────────────────────────────────────────────────┘

Step 1: Define Workflow in YAML
┌────────────────────────────────────────┐
│  workflow.yaml                         │
│                                        │
│  name: ResearchWorkflow                │
│  agents:                               │
│    - name: researcher                  │
│      type: OpenAI                      │
│  executors:                            │
│    - id: research                      │
│      agent: researcher                 │
│  edges:                                │
│    - from: START                       │
│      to: research                      │
│      condition: "true"                 │
└────────┬───────────────────────────────┘
         │
         │ (1) Load file
         ▼
┌────────────────────────────────────────┐
│  DeclarativeWorkflowLanguage           │
│  (Parser)                              │
│                                        │
│  • Read YAML                           │
│  • Validate schema                    │
│  • Check syntax                        │
└────────┬───────────────────────────────┘
         │
         │ (2) Parse & Validate
         ▼

Step 2: Create Object Model
┌────────────────────────────────────────┐
│  Workflow ObjectModel                  │
│  (In-Memory Representation)            │
│                                        │
│  ┌──────────────────────────────────┐ │
│  │  Agents                          │ │
│  │  • Name                          │ │
│  │  • Type                          │ │
│  │  • Configuration                 │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │  Executors                       │ │
│  │  • ID                            │ │
│  │  • Agent reference               │ │
│  │  • Parameters                    │ │
│  └──────────────────────────────────┘ │
│  ┌──────────────────────────────────┐ │
│  │  Edges                           │ │
│  │  • From/To nodes                 │ │
│  │  • Conditions (PowerFx)          │ │
│  └──────────────────────────────────┘ │
└────────┬───────────────────────────────┘
         │
         │ (3) Build workflow
         ▼

Step 3: Resolve Dependencies
┌────────────────────────────────────────┐
│  DeclarativeWorkflowBuilder            │
└────────┬───────────────────────────────┘
         │
         │ (4) Lookup agents
         ▼
┌────────────────────────────────────────┐
│  Agent Catalog                         │
│  (Dependency Injection)                │
│                                        │
│  agents = {                            │
│    "researcher": ResearcherAgent,      │
│    "writer": WriterAgent,              │
│    "reviewer": ReviewerAgent           │
│  }                                     │
└────────┬───────────────────────────────┘
         │
         │ (5) Return agent instances
         ▼
┌────────────────────────────────────────┐
│  DeclarativeWorkflowBuilder            │
│                                        │
│  • Map YAML agents to real agents     │
│  • Create executor instances          │
│  • Wire up edges                       │
│  • Compile PowerFx expressions         │
└────────┬───────────────────────────────┘
         │
         │ (6) Generate
         ▼

Step 4: Create Executable Workflow
┌────────────────────────────────────────┐
│  Workflow (Executable)                 │
│                                        │
│  Graph structure:                      │
│                                        │
│    START                               │
│      ↓                                 │
│   [Researcher]                         │
│      ↓                                 │
│   [Writer]                             │
│      ↓                                 │
│   [Reviewer]                           │
│      ↓                                 │
│    END                                 │
└────────┬───────────────────────────────┘
         │
         │ (7) RunAsync()
         ▼
    [Execute like any workflow]
    (See Workflow Execution diagram)

═══════════════════════════════════════════════════════════════════════════
YAML TO CODE TRANSFORMATION
═══════════════════════════════════════════════════════════════════════════

YAML:                           CODE EQUIVALENT:
┌──────────────────────────┐   ┌────────────────────────────────┐
│ agents:                  │   │ var researcher =               │
│   - name: researcher     │   │   chatClient.CreateAIAgent()   │
│     model: gpt-4         │   │   .WithModel("gpt-4")          │
│                          │   │   .Build();                    │
├──────────────────────────┤   ├────────────────────────────────┤
│ executors:               │   │ var workflow =                 │
│   - id: research         │   │   WorkflowBuilder.Create()     │
│     agent: researcher    │   │   .AddExecutor(                │
│                          │   │     "research",                │
│                          │   │     researcher                 │
│                          │   │   )                            │
├──────────────────────────┤   ├────────────────────────────────┤
│ edges:                   │   │   .AddEdge(                    │
│   - from: START          │   │     "START",                   │
│     to: research         │   │     "research",                │
│     condition: "true"    │   │     condition: "true"          │
│                          │   │   )                            │
│                          │   │   .Build();                    │
└──────────────────────────┘   └────────────────────────────────┘
```

---

## 4. A2A (Agent-to-Agent) Communication - Component Interaction

**Flow:** Client Agent → Network → Server Agent → Target Agent → Response

```
┌─────────────────────────────────────────────────────────────────────────┐
│                  A2A AGENT-TO-AGENT COMMUNICATION                       │
└─────────────────────────────────────────────────────────────────────────┘

CLIENT SIDE                                    SERVER SIDE
═══════════════════════════════════════════════════════════════════════════

┌──────────────────┐
│  Client App      │
└────────┬─────────┘
         │
         │ (1) Create connection
         ▼
┌──────────────────────────┐
│  A2AAgent (Client)       │
│                          │
│  • Configure endpoint    │
│  • Set credentials       │
│  • Define protocol       │
└────────┬─────────────────┘
         │
         │ (2) SendAsync(message)
         │
         │ Convert to A2A format:
         │ {
         │   "type": "message",
         │   "content": "...",
         │   "metadata": {...}
         │ }
         │
         ▼
┌──────────────────────────┐
│      Network             │
│      (HTTP/HTTPS)        │
│                          │
│  POST /api/agents/chat   │
│  Content-Type:           │
│    application/json      │
└────────┬─────────────────┘
         │
         │ (3) HTTP Request
         │
         ├────────────────────────────────────────┐
         │                                        │
         │                        ┌───────────────▼──────────┐
         │                        │  ASP.NET Core Endpoint   │
         │                        │  (A2A.AspNetCore)        │
         │                        │                          │
         │                        │  • Receive HTTP request  │
         │                        │  • Deserialize A2A msg   │
         │                        │  • Validate protocol     │
         │                        └───────────┬──────────────┘
         │                                    │
         │                                    │ (4) Process
         │                                    ▼
         │                        ┌───────────────────────────┐
         │                        │  A2AHostAgent             │
         │                        │  (Protocol Handler)       │
         │                        └───────────┬───────────────┘
         │                                    │
         │                                    │ (5) Store message
         │                                    ▼
         │                        ┌───────────────────────────┐
         │                        │  Message Store            │
         │                        │  (Thread persistence)     │
         │                        └───────────┬───────────────┘
         │                                    │
         │                                    │ (6) Invoke
         │                                    ▼
         │                        ┌───────────────────────────┐
         │                        │  Target Agent             │
         │                        │  (Your actual agent)      │
         │                        │                           │
         │                        │  • Process message        │
         │                        │  • Call LLM if needed     │
         │                        │  • Execute tools          │
         │                        │  • Generate response      │
         │                        └───────────┬───────────────┘
         │                                    │
         │                                    │ (7) Response
         │                                    ▼
         │                        ┌───────────────────────────┐
         │                        │  A2AHostAgent             │
         │                        │  • Store response         │
         │                        │  • Convert to A2A format  │
         │                        └───────────┬───────────────┘
         │                                    │
         │                                    │ (8) Return
         │                                    ▼
         │                        ┌───────────────────────────┐
         │                        │  ASP.NET Core Endpoint    │
         │                        │  • Serialize response     │
         │                        │  • Send HTTP response     │
         │                        └───────────┬───────────────┘
         │                                    │
         │◄───────────────────────────────────┘
         │
         │ (9) HTTP Response
         ▼
┌──────────────────────────┐
│  A2AAgent (Client)       │
│  • Deserialize response  │
│  • Convert to internal   │
└────────┬─────────────────┘
         │
         │ (10) Return AgentRunResponse
         ▼
┌──────────────────┐
│  Client App      │
│  • Display result│
└──────────────────┘

═══════════════════════════════════════════════════════════════════════════
A2A MESSAGE FORMAT EXAMPLE
═══════════════════════════════════════════════════════════════════════════

REQUEST:                          RESPONSE:
┌──────────────────────────────┐  ┌──────────────────────────────┐
│ {                            │  │ {                            │
│   "type": "message",         │  │   "type": "response",        │
│   "id": "msg-123",           │  │   "id": "resp-123",          │
│   "threadId": "thread-1",    │  │   "threadId": "thread-1",    │
│   "content": {               │  │   "content": {               │
│     "role": "user",          │  │     "role": "assistant",     │
│     "text": "Hello"          │  │     "text": "Hi there!"      │
│   },                         │  │   },                         │
│   "metadata": {              │  │   "metadata": {              │
│     "timestamp": "..."       │  │     "timestamp": "...",      │
│   }                          │  │     "modelUsed": "gpt-4"     │
│ }                            │  │   }                          │
└──────────────────────────────┘  │ }                            │
                                   └──────────────────────────────┘
```

---

## 5. Hosting Layer - Component Relationships

**Purpose:** Dependency Injection, Agent Registration, and HTTP Hosting

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        HOSTING LAYER ARCHITECTURE                       │
└─────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────┐
│                         APPLICATION LAYER                             │
│                                                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  Application Code (Blazor / ASP.NET / Console)                  │ │
│  │                                                                  │ │
│  │  • Register agents during startup                               │ │
│  │  • Request agents at runtime                                    │ │
│  └──────┬────────────────────────────────────────┬─────────────────┘ │
│         │                                        │                   │
└─────────┼────────────────────────────────────────┼───────────────────┘
          │                                        │
          │ Register                               │ Request
          │                                        │
┌─────────▼────────────────────────────────────────▼───────────────────┐
│                           HOSTING LAYER                              │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │         Dependency Injection Container                       │  │
│  │                                                              │  │
│  │  services.AddAgent<MyAgent>();                              │  │
│  │  services.AddAgentCatalog();                                │  │
│  │  services.AddChatClient(...);                               │  │
│  └────────┬─────────────────────────────────────────┬──────────┘  │
│           │                                         │             │
│           │ Manages                                 │ Resolves    │
│           ▼                                         ▼             │
│  ┌──────────────────┐                   ┌──────────────────────┐ │
│  │ LocalAgent       │◄──────────────────│  Agent Catalog       │ │
│  │ Registry         │     Queries        │                      │ │
│  │                  │                    │  • Lookup by name    │ │
│  │ • Agent types    │                    │  • Agent metadata    │ │
│  │ • Registrations  │                    │  • Discovery         │ │
│  └──────────────────┘                    └──────────────────────┘ │
│                                                                      │
│  ┌──────────────────────────────────────────────────────────────┐  │
│  │              Hosting Extensions                              │  │
│  │                                                              │  │
│  │  ┌────────────────────┐         ┌───────────────────────┐  │  │
│  │  │ Hosting.A2A        │         │ Hosting.OpenAI        │  │  │
│  │  │ .AspNetCore        │         │                       │  │  │
│  │  │                    │         │                       │  │  │
│  │  │ • A2A endpoints    │         │ • OpenAI-compatible   │  │  │
│  │  │ • Protocol handler │         │   API endpoints       │  │  │
│  │  └────────┬───────────┘         └────────┬──────────────┘  │  │
│  │           │                               │                 │  │
│  └───────────┼───────────────────────────────┼─────────────────┘  │
│              │ Expose via HTTP               │                    │
└──────────────┼───────────────────────────────┼────────────────────┘
               │                               │
               │                               │
┌──────────────▼───────────────────────────────▼────────────────────┐
│                     CORE AGENT LAYER                              │
│                                                                   │
│  ┌──────────────────┐                  ┌──────────────────────┐ │
│  │ AIAgentBuilder   │──────builds─────>│     AIAgent          │ │
│  │                  │                  │                      │ │
│  │ • Fluent API     │                  │ • Core logic         │ │
│  │ • Configuration  │                  │ • Wrapped with       │ │
│  └──────────────────┘                  │   decorators         │ │
│           ▲                             └──────────┬───────────┘ │
│           │ Injected                               │             │
│           │                                        │ Delegates   │
└───────────┼────────────────────────────────────────┼─────────────┘
            │                                        │
            │                                        │
┌───────────┴────────────────────────────────────────▼─────────────┐
│                      PROVIDER LAYER                              │
│                                                                  │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │  AI.OpenAI   │  │  AI.AzureAI  │  │   AI.A2A     │          │
│  │              │  │              │  │              │          │
│  │ • OpenAI API │  │ • Azure AI   │  │ • A2A        │          │
│  │   wrapper    │  │   wrapper    │  │   protocol   │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
└──────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════
REGISTRATION AND RESOLUTION FLOW
═══════════════════════════════════════════════════════════════════════════

STARTUP (Registration):              RUNTIME (Resolution):

1. services.AddAgent<MyAgent>()      1. Request agent from catalog
         │                                      │
         ▼                                      ▼
2. Register in DI container           2. Catalog queries registry
         │                                      │
         ▼                                      ▼
3. Add to LocalAgentRegistry          3. DI container creates instance
         │                                      │
         ▼                                      ▼
4. Configure dependencies             4. Inject dependencies
         │                                      │
         ▼                                      ▼
5. Ready for use                      5. Return agent instance
```

---

## 6. Complete Message Flow Through All Layers

**Flow:** User → App → Hosting → Agent → Workflow → Provider → LLM → Back

```
┌─────────────────────────────────────────────────────────────────────────┐
│                   COMPLETE END-TO-END MESSAGE FLOW                      │
└─────────────────────────────────────────────────────────────────────────┘

              ┌─────────────────────────────┐
              │      [USER MESSAGE]         │
              └─────────────┬───────────────┘
                            │
                            ▼
╔═════════════════════════════════════════════════════════════════════════╗
║                        APPLICATION LAYER                                ║
╚═════════════════════════════════════════════════════════════════════════╝
                ┌───────────────────────────┐
                │  Blazor / ASP.NET /       │
                │  Console Application      │
                └─────────────┬─────────────┘
                              │
                ┌─────────────┴─────────────┐
                │                           │
         Is hosted via HTTP?           Direct call?
                │                           │
                ▼                           ▼
    ┌──────────────────┐          ┌──────────────────┐
    │  HTTP Request    │          │  Direct Method   │
    └────────┬─────────┘          └────────┬─────────┘
             │                              │
╔═══════════▼══════════════════════════════▼═════════════════════════════╗
║                         HOSTING LAYER (Optional)                       ║
╚════════════════════════════════════════════════════════════════════════╝
    ┌────────────────────┐
    │  HTTP Endpoint     │
    │  (A2A/OpenAI)      │
    └────────┬───────────┘
             │
    ┌────────▼───────────┐
    │  Agent Catalog     │
    │  (Resolve by name) │
    └────────┬───────────┘
             │
             └────────────────────────┐
                                      │
╔═════════════════════════════════════▼═══════════════════════════════════╗
║                       CORE AGENT LAYER                                  ║
╚═════════════════════════════════════════════════════════════════════════╝
                    ┌──────────────────┐
                    │    AIAgent       │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  OpenTelemetry   │  ◄─── Tracing/Metrics
                    │  Wrapper         │
                    └────────┬─────────┘
                             │
                    ┌────────▼─────────┐
                    │  Function        │  ◄─── Tool handling
                    │  Invocation      │
                    │  Handler         │
                    └────────┬─────────┘
                             │
                ┌────────────┴────────────┐
                │                         │
         Is Workflow Agent?          Single Agent?
                │                         │
                ▼                         │
╔═══════════════════════════════════════╗ │
║      WORKFLOW LAYER (Optional)        ║ │
╚═══════════════════════════════════════╝ │
    ┌──────────────────┐                  │
    │  Workflow        │                  │
    │  Runner          │                  │
    └────────┬─────────┘                  │
             │                            │
    ┌────────▼─────────┐                  │
    │  Execute         │                  │
    │  Executors       │                  │
    │  (in order)      │                  │
    └────────┬─────────┘                  │
             │                            │
    ┌────────▼─────────┐                  │
    │  State           │                  │
    │  Management      │                  │
    └────────┬─────────┘                  │
             │                            │
             └────────────────────────────┘
                          │
╔═════════════════════════▼═══════════════════════════════════════════════╗
║                       PROVIDER LAYER                                    ║
╚═════════════════════════════════════════════════════════════════════════╝
         ┌───────────────────────────────────────────┐
         │    Provider Implementation                │
         │  ┌─────────┐  ┌─────────┐  ┌─────────┐   │
         │  │ OpenAI  │  │ AzureAI │  │   A2A   │   │
         │  └─────────┘  └─────────┘  └─────────┘   │
         └───────────────────┬───────────────────────┘
                             │
╔═════════════════════════════▼═══════════════════════════════════════════╗
║                    EXTERNAL SDK LAYER                                   ║
╚═════════════════════════════════════════════════════════════════════════╝
                    ┌──────────────────┐
                    │  External SDK    │
                    │  (OpenAI, Azure) │
                    └────────┬─────────┘
                             │
                             │ API Call
                             ▼
                    ┌──────────────────┐
                    │  External LLM    │
                    │  (GPT-4, etc)    │
                    └────────┬─────────┘
                             │
                             │ Response
                             ▼

═══════════════════════ RETURN PATH ═══════════════════════════════════════

                    ┌──────────────────┐
                    │  [LLM RESPONSE]  │
                    └────────┬─────────┘
                             │
                             ▼
            External SDK → Provider → Core Agent
                             │
                    ┌────────┴─────────┐
                    │                  │
            Was Workflow?       Single Agent?
                    │                  │
                    ▼                  ▼
         Workflow Runner ─────────> Function Handler
                    │                  │
                    └─────────┬────────┘
                              │
                              ▼
                    OpenTelemetry Wrapper
                              │
                              ▼
                         AIAgent
                              │
                    ┌─────────┴──────────┐
                    │                    │
            Was Hosted?            Direct call?
                    │                    │
                    ▼                    ▼
            HTTP Response          Application
                    │                    │
                    └─────────┬──────────┘
                              │
                              ▼
                   ┌─────────────────────┐
                   │  [USER RESPONSE]    │
                   └─────────────────────┘

═══════════════════════════════════════════════════════════════════════════
DECISION POINTS IN THE FLOW
═══════════════════════════════════════════════════════════════════════════

Decision 1: Is the agent hosted via HTTP?
  YES → Go through Hosting Layer (HTTP Endpoint + Catalog)
  NO  → Direct method call to agent

Decision 2: Is this a workflow agent?
  YES → Execute through Workflow Layer with multiple executors
  NO  → Single agent execution

Decision 3: Does the response require tool calls?
  YES → Function Handler executes tools and calls LLM again
  NO  → Return response immediately

Decision 4: Was the agent accessed via HTTP?
  YES → Return HTTP response
  NO  → Return directly to application
```

---

## 7. Tool/Function Invocation Flow

**Flow:** Agent → LLM (requests tools) → Execute Tools → LLM (with results) → Response

```
┌─────────────────────────────────────────────────────────────────────────┐
│                     TOOL/FUNCTION INVOCATION FLOW                       │
└─────────────────────────────────────────────────────────────────────────┘

Step 1: Initial Request
┌──────────────────┐
│   Application    │
└────────┬─────────┘
         │
         │ RunAsync("What's the weather in Seattle?")
         ▼
┌────────────────────────────┐
│       AIAgent              │
└────────┬───────────────────┘
         │
         │ Delegate to function handler
         ▼
┌────────────────────────────────────┐
│  FunctionInvocationDelegatingAgent │
│                                    │
│  • Intercepts agent execution      │
│  • Manages tool calls              │
└────────┬───────────────────────────┘
         │
         │ Forward request
         ▼

Step 2: First LLM Call (with tool definitions)
┌────────────────────────────────────┐
│      Provider                      │
│      (OpenAI/AzureAI)              │
└────────┬───────────────────────────┘
         │
         │ Send message + tool definitions:
         │ {
         │   message: "What's the weather...",
         │   tools: [
         │     { name: "get_weather",
         │       parameters: {...} }
         │   ]
         │ }
         ▼
┌────────────────────────────────────┐
│      External LLM                  │
│      (GPT-4, etc)                  │
└────────┬───────────────────────────┘
         │
         │ Response: Tool call needed!
         │ {
         │   tool_calls: [{
         │     name: "get_weather",
         │     arguments: {
         │       "city": "Seattle"
         │     }
         │   }]
         │ }
         ▼
┌────────────────────────────────────┐
│  FunctionInvocationDelegatingAgent │
│  Detects tool_calls in response   │
└────────┬───────────────────────────┘
         │
         │ (Loop for each tool call)
         ▼

Step 3: Execute Tools
╔════════════════════════════════════════════════════════════════╗
║                    TOOL EXECUTION LOOP                         ║
╚════════════════════════════════════════════════════════════════╝

    ┌────────────────────────────────┐
    │  Function Handler              │
    │  Parse tool call:              │
    │  • Tool name: "get_weather"    │
    │  • Arguments: {"city":"..."}   │
    └────────┬───────────────────────┘
             │
             │ (1) Resolve tool from DI
             ▼
    ┌────────────────────────────────┐
    │  Dependency Injection          │
    │  Container                     │
    │                                │
    │  GetService<IWeatherTool>()    │
    └────────┬───────────────────────┘
             │
             │ (2) Return tool instance
             ▼
    ┌────────────────────────────────┐
    │  Tool Implementation           │
    │  (Weather Service)             │
    │                                │
    │  public async Task<string>     │
    │  GetWeatherAsync(string city)  │
    │  {                             │
    │    // Call weather API         │
    │    return weather_data;        │
    │  }                             │
    └────────┬───────────────────────┘
             │
             │ (3) InvokeAsync(arguments)
             │
             │ Executes tool logic:
             │ • Validate inputs
             │ • Call external API
             │ • Format result
             │
             │ (4) Return result
             ▼
    ┌────────────────────────────────┐
    │  Tool Result                   │
    │                                │
    │  "Temperature: 65°F,           │
    │   Conditions: Partly cloudy"   │
    └────────┬───────────────────────┘
             │
             │ (5) Append to message history
             ▼
    ┌────────────────────────────────┐
    │  Function Handler              │
    │  Messages:                     │
    │  1. User: "What's weather..."  │
    │  2. Assistant: [tool_call]     │
    │  3. Tool: "Temperature: 65°F"  │
    └────────┬───────────────────────┘
             │
             └───> [Repeat for other tools if multiple]

Step 4: Second LLM Call (with tool results)
┌────────────────────────────────────┐
│  FunctionInvocationDelegatingAgent │
│  Send updated messages             │
└────────┬───────────────────────────┘
         │
         │ Continue conversation with tool results
         ▼
┌────────────────────────────────────┐
│      Provider                      │
└────────┬───────────────────────────┘
         │
         │ Send messages including tool results
         ▼
┌────────────────────────────────────┐
│      External LLM                  │
└────────┬───────────────────────────┘
         │
         │ Final Response (text):
         │ "The weather in Seattle is
         │  partly cloudy with a
         │  temperature of 65°F."
         ▼
┌────────────────────────────────────┐
│      Provider                      │
└────────┬───────────────────────────┘
         │
         │ No more tool calls needed
         ▼
┌────────────────────────────────────┐
│  FunctionInvocationDelegatingAgent │
└────────┬───────────────────────────┘
         │
         │ Return final response
         ▼
┌────────────────────────────────────┐
│       AIAgent                      │
└────────┬───────────────────────────┘
         │
         │ AgentRunResponse
         ▼
┌──────────────────┐
│   Application    │
│                  │
│  Display: "The   │
│  weather in..."  │
└──────────────────┘

═══════════════════════════════════════════════════════════════════════════
TOOL EXECUTION TIMELINE
═══════════════════════════════════════════════════════════════════════════

Time  Component           Action
────  ──────────────────  ───────────────────────────────────────────
t0    Application         Send: "What's the weather in Seattle?"
t1    Agent               Forward to function handler
t2    Function Handler    Forward with tool definitions
t3    LLM                 Return: TOOL_CALL(get_weather, "Seattle")
t4    Function Handler    Resolve tool from DI container
t5    DI Container        Return weather tool instance
t6    Weather Tool        Execute: Call weather API
t7    Weather Tool        Return: "65°F, Partly cloudy"
t8    Function Handler    Append result to messages
t9    Function Handler    Send messages back to LLM
t10   LLM                 Generate natural language response
t11   Agent               Return final response to app
```

---

## 8. Multi-Agent Workflow Interaction

**Flow:** Input → Workflow → Multiple Agents (Orchestrated) → Output

```
┌─────────────────────────────────────────────────────────────────────────┐
│              MULTI-AGENT WORKFLOW ORCHESTRATION                         │
└─────────────────────────────────────────────────────────────────────────┘

                       ┌─────────────────────┐
                       │   [USER INPUT]      │
                       │  "Write article     │
                       │   about AI"         │
                       └──────────┬──────────┘
                                  │
                                  ▼
╔═════════════════════════════════════════════════════════════════════════╗
║                      WORKFLOW ORCHESTRATOR                              ║
╚═════════════════════════════════════════════════════════════════════════╝
        ┌───────────────────────────────────────────────────┐
        │             Workflow                              │
        │  • Entry point                                    │
        │  • Exit conditions                                │
        │  • Error handling                                 │
        └────────────┬──────────────────────────────────────┘
                     │
        ┌────────────▼──────────────────────────────────────┐
        │          Message Router                           │
        │  • Evaluate conditions                            │
        │  • Route to executors                             │
        │  • Handle responses                               │
        └────────────┬──────────────────────────────────────┘
                     │
         ┌───────────┼───────────┐
         │           │           │
         ▼           ▼           ▼
    ┌────────┐  ┌────────┐  ┌────────┐
    │Step 1  │  │Step 2  │  │Step 3  │
    └────────┘  └────────┘  └────────┘
         │           │           │
         │           │           │
         └───────────┼───────────┘
                     │
        ┌────────────▼──────────────────────────────────────┐
        │          State Manager                            │
        │  • Shared context                                 │
        │  • Message history                                │
        │  • Execution state                                │
        └───────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════
SEQUENTIAL MULTI-AGENT EXECUTION
═══════════════════════════════════════════════════════════════════════════

STEP 1: Research Phase
┌────────────────────────────────────────┐
│  Executor 1: Researcher                │
│  (Agent Executor Wrapper)              │
└────────┬───────────────────────────────┘
         │
         │ Invoke agent
         ▼
┌────────────────────────────────────────┐
│  Researcher AIAgent                    │
│  Instructions: "Research topics..."    │
└────────┬───────────────────────────────┘
         │
         │ Call provider
         ▼
┌────────────────────────────────────────┐
│  OpenAI Provider                       │
│  Model: gpt-4                          │
└────────┬───────────────────────────────┘
         │
         │ API Call
         ▼
┌────────────────────────────────────────┐
│  OpenAI API                            │
└────────┬───────────────────────────────┘
         │
         │ Response: Research data
         │ "AI is transforming..."
         ▼
┌────────────────────────────────────────┐
│  State Manager                         │
│  Save: research_data                   │
└────────────────────────────────────────┘

                    │
                    │ Route to next
                    ▼

STEP 2: Writing Phase
┌────────────────────────────────────────┐
│  Executor 2: Writer                    │
│  (Agent Executor Wrapper)              │
└────────┬───────────────────────────────┘
         │
         │ Get research_data from state
         │
         │ Invoke agent
         ▼
┌────────────────────────────────────────┐
│  Writer AIAgent                        │
│  Instructions: "Write article using..."│
│  Context: [research_data]              │
└────────┬───────────────────────────────┘
         │
         │ Call provider
         ▼
┌────────────────────────────────────────┐
│  Azure OpenAI Provider                 │
│  Model: gpt-4                          │
└────────┬───────────────────────────────┘
         │
         │ API Call
         ▼
┌────────────────────────────────────────┐
│  Azure OpenAI API                      │
└────────┬───────────────────────────────┘
         │
         │ Response: Article draft
         │ "# AI Revolution\n\nAI is..."
         ▼
┌────────────────────────────────────────┐
│  State Manager                         │
│  Save: article_draft                   │
└────────────────────────────────────────┘

                    │
                    │ Route to next
                    ▼

STEP 3: Review Phase
┌────────────────────────────────────────┐
│  Executor 3: Reviewer                  │
│  (Agent Executor Wrapper)              │
└────────┬───────────────────────────────┘
         │
         │ Get article_draft from state
         │
         │ Invoke agent
         ▼
┌────────────────────────────────────────┐
│  Reviewer AIAgent                      │
│  Instructions: "Review and improve..." │
│  Context: [article_draft]              │
└────────┬───────────────────────────────┘
         │
         │ Call provider
         ▼
┌────────────────────────────────────────┐
│  OpenAI Provider                       │
│  Model: gpt-4                          │
└────────┬───────────────────────────────┘
         │
         │ API Call
         ▼
┌────────────────────────────────────────┐
│  OpenAI API                            │
└────────┬───────────────────────────────┘
         │
         │ Response: Reviewed article
         │ + Suggestions
         ▼
┌────────────────────────────────────────┐
│  State Manager                         │
│  Save: final_article                   │
└────────┬───────────────────────────────┘
         │
         │ Check exit condition
         ▼
    [Workflow Complete]
         │
         ▼
┌────────────────────────────────────────┐
│   [FINAL OUTPUT]                       │
│   Polished article ready               │
└────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════
STATE SHARING BETWEEN AGENTS
═══════════════════════════════════════════════════════════════════════════

State Manager (Shared Context):
┌──────────────────────────────────────────────────────────┐
│  {                                                       │
│    "input": "Write article about AI",                   │
│    "research_data": "AI is transforming...",  ◄─ Step 1 │
│    "article_draft": "# AI Revolution...",     ◄─ Step 2 │
│    "final_article": "# AI Revolution...",     ◄─ Step 3 │
│    "metadata": {                                         │
│      "researcher_model": "gpt-4",                        │
│      "writer_model": "gpt-4",                            │
│      "reviewer_model": "gpt-4"                           │
│    }                                                     │
│  }                                                       │
└──────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════
CONDITIONAL ROUTING EXAMPLE
═══════════════════════════════════════════════════════════════════════════

                    ┌─────────────┐
                    │  Reviewer   │
                    └──────┬──────┘
                           │
                   Check quality score
                           │
           ┌───────────────┴───────────────┐
           │                               │
      Score < 8?                      Score >= 8?
           │                               │
           ▼                               ▼
    ┌──────────┐                    ┌──────────┐
    │  Writer  │  ◄─── Revise       │  Output  │
    │ (retry)  │                    │  (done)  │
    └──────────┘                    └──────────┘
```

---

## 9. Dependency Injection and Agent Resolution

**Flow:** Startup Registration → Runtime Resolution → Agent Creation

```
┌─────────────────────────────────────────────────────────────────────────┐
│             DEPENDENCY INJECTION & AGENT RESOLUTION                     │
└─────────────────────────────────────────────────────────────────────────┘

╔═════════════════════════════════════════════════════════════════════════╗
║                        STARTUP PHASE                                    ║
╚═════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────┐
│  Application Startup                 │
│  (Program.cs / Startup.cs)           │
└────────┬─────────────────────────────┘
         │
         │ ConfigureServices()
         ▼
┌────────────────────────────────────────────────────────┐
│  IServiceCollection                                    │
│                                                        │
│  // Register agents                                    │
│  services.AddAgent<MyAgent>();                         │
│  services.AddAgent<ResearcherAgent>();                 │
│                                                        │
│  // Register catalog                                   │
│  services.AddAgentCatalog();                           │
│                                                        │
│  // Register chat clients                              │
│  services.AddOpenAIChatClient(config);                 │
│  services.AddAzureAIChatClient(config);                │
│                                                        │
│  // Register tools                                     │
│  services.AddSingleton<IWeatherTool, WeatherTool>();   │
│                                                        │
│  // Register storage                                   │
│  services.AddSingleton<ChatMessageStore>();            │
│                                                        │
│  // Register logging                                   │
│  services.AddLogging();                                │
└────────┬───────────────────────────────────────────────┘
         │
         │ Build container
         ▼
┌────────────────────────────────────────────────────────┐
│  Dependency Injection Container                        │
│  (Built & Ready)                                       │
│                                                        │
│  Service Registry:                                     │
│  ┌──────────────────────────────────────────────────┐ │
│  │ IServiceProvider                                 │ │
│  │  • MyAgent            → Transient/Scoped         │ │
│  │  • ResearcherAgent    → Transient/Scoped         │ │
│  │  • AgentCatalog       → Singleton                │ │
│  │  • IChatClient        → Singleton                │ │
│  │  • IWeatherTool       → Singleton                │ │
│  │  • ChatMessageStore   → Singleton                │ │
│  │  • ILogger            → Singleton                │ │
│  └──────────────────────────────────────────────────┘ │
└────────────────────────────────────────────────────────┘

╔═════════════════════════════════════════════════════════════════════════╗
║                        RUNTIME PHASE                                    ║
╚═════════════════════════════════════════════════════════════════════════╝

┌──────────────────────────────────────┐
│  Request Handler                     │
│  (Controller / Service)              │
└────────┬─────────────────────────────┘
         │
         │ Need agent: "MyAgent"
         ▼
┌────────────────────────────────────────────────────────┐
│  Agent Catalog                                         │
│                                                        │
│  var agent = await catalog                             │
│    .GetAgentAsync("MyAgent");                          │
└────────┬───────────────────────────────────────────────┘
         │
         │ Lookup by name
         ▼
┌────────────────────────────────────────────────────────┐
│  LocalAgentRegistry                                    │
│  • Find agent type by name                             │
│  • Get registration info                               │
└────────┬───────────────────────────────────────────────┘
         │
         │ Request from DI: GetService<MyAgent>()
         ▼
┌────────────────────────────────────────────────────────┐
│  DI Container                                          │
│  Create new instance of MyAgent                        │
└────────┬───────────────────────────────────────────────┘
         │
         │ Resolve dependencies
         ▼

╔════════════════════════════════════════════════════════════════╗
║                  DEPENDENCY RESOLUTION                         ║
╚════════════════════════════════════════════════════════════════╝

    Constructor: MyAgent(
        IChatClient chatClient,
        IWeatherTool weatherTool,
        ChatMessageStore messageStore,
        ILogger<MyAgent> logger
    )
    
    Resolve each parameter:
    
    ┌─────────────────────────────────────┐
    │  1. Resolve IChatClient             │
    │     → Get OpenAI chat client        │
    └─────────────┬───────────────────────┘
                  │
    ┌─────────────▼───────────────────────┐
    │  2. Resolve IWeatherTool            │
    │     → Get WeatherTool instance      │
    └─────────────┬───────────────────────┘
                  │
    ┌─────────────▼───────────────────────┐
    │  3. Resolve ChatMessageStore        │
    │     → Get singleton instance        │
    └─────────────┬───────────────────────┘
                  │
    ┌─────────────▼───────────────────────┐
    │  4. Resolve ILogger<MyAgent>        │
    │     → Create logger                 │
    └─────────────┬───────────────────────┘
                  │
                  │ All dependencies resolved
                  ▼
    ┌─────────────────────────────────────┐
    │  Construct MyAgent                  │
    │                                     │
    │  new MyAgent(                       │
    │    chatClient: openAiClient,        │
    │    weatherTool: weatherTool,        │
    │    messageStore: store,             │
    │    logger: logger                   │
    │  )                                  │
    └─────────────┬───────────────────────┘
                  │
                  │ Agent instance created
                  ▼
┌────────────────────────────────────────────────────────┐
│  MyAgent Instance                                      │
│  (Fully initialized with all dependencies)             │
└────────┬───────────────────────────────────────────────┘
         │
         │ Return to catalog
         ▼
┌────────────────────────────────────────────────────────┐
│  Agent Catalog                                         │
└────────┬───────────────────────────────────────────────┘
         │
         │ Return to request handler
         ▼
┌────────────────────────────────────────────────────────┐
│  Request Handler                                       │
│                                                        │
│  var response = await agent.RunAsync(message);         │
└────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════
LIFETIME SCOPES
═══════════════════════════════════════════════════════════════════════════

Singleton (App lifetime):
  • AgentCatalog
  • IChatClient
  • ChatMessageStore
  • Configuration

Scoped (Request lifetime):
  • AgentThread
  • Request-specific state

Transient (New instance each time):
  • AIAgent instances
  • Executors

═══════════════════════════════════════════════════════════════════════════
REGISTRATION PATTERNS
═══════════════════════════════════════════════════════════════════════════

1. Direct Registration:
   services.AddAgent<MyAgent>();

2. Factory Registration:
   services.AddAgent<MyAgent>(sp => {
       var client = sp.GetRequiredService<IChatClient>();
       return new MyAgent(client);
   });

3. Named Registration:
   services.AddAgent<MyAgent>("my-agent-name");

4. With Options:
   services.AddAgent<MyAgent>(options => {
       options.Name = "MyAgent";
       options.Description = "...";
   });
```

---

## 10. Cross-Cutting Concerns Flow

**Purpose:** Observability, Logging, Security, Storage - concerns that span all layers

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    CROSS-CUTTING CONCERNS PIPELINE                      │
└─────────────────────────────────────────────────────────────────────────┘

                        ┌─────────────────┐
                        │  [REQUEST IN]   │
                        └────────┬────────┘
                                 │
╔════════════════════════════════▼═════════════════════════════════════════╗
║                     LAYER 1: OBSERVABILITY                               ║
╚══════════════════════════════════════════════════════════════════════════╝
                 ┌────────────────────────────┐
                 │  OpenTelemetry Wrapper     │
                 │                            │
                 │  • Start trace/span        │
                 │  • Record start time       │
                 │  • Add trace context       │
                 └────────┬───────────────────┘
                          │
                 ┌────────▼───────────────────┐
                 │  Emit Start Event          │
                 │  TraceId: abc-123          │
                 │  Operation: agent.run      │
                 └────────┬───────────────────┘
                          │
╔════════════════════════▼══════════════════════════════════════════════════╗
║                     LAYER 2: MIDDLEWARE / SECURITY                        ║
╚═══════════════════════════════════════════════════════════════════════════╝
                 ┌────────────────────────────┐
                 │  Delegating Agent Chain    │
                 │  (Middleware Pipeline)     │
                 └────────┬───────────────────┘
                          │
                 ┌────────▼───────────────────┐
                 │  1. Authentication         │
                 │     • Verify credentials   │
                 │     • Check API key        │
                 └────────┬───────────────────┘
                          │
                 ┌────────▼───────────────────┐
                 │  2. Authorization          │
                 │     • Check permissions    │
                 │     • Validate scope       │
                 └────────┬───────────────────┘
                          │
                 ┌────────▼───────────────────┐
                 │  3. Validation             │
                 │     • Input validation     │
                 │     • Schema check         │
                 └────────┬───────────────────┘
                          │
╔════════════════════════▼══════════════════════════════════════════════════╗
║                     LAYER 3: FUNCTION HANDLING                            ║
╚═══════════════════════════════════════════════════════════════════════════╝
                 ┌────────────────────────────┐
                 │  Function Invocation       │
                 │  Handler                   │
                 │                            │
                 │  • Detect tool calls       │
                 │  • Execute tools           │
                 │  • Handle results          │
                 └────────┬───────────────────┘
                          │
                 ┌────────▼───────────────────┐
                 │  Human Approval Gates      │
                 │  (if configured)           │
                 │                            │
                 │  • Pause execution         │
                 │  • Request approval        │
                 │  • Wait for response       │
                 └────────┬───────────────────┘
                          │
╔════════════════════════▼══════════════════════════════════════════════════╗
║                     LAYER 4: CORE AGENT                                   ║
╚═══════════════════════════════════════════════════════════════════════════╝
                 ┌────────────────────────────┐
                 │  Core Agent Logic          │
                 │                            │
                 │  • Process input           │
                 │  • Call provider           │
                 │  • Generate response       │
                 └────────┬───────────────────┘
                          │
                          │ Call LLM
                          ▼
                 ┌────────────────────────────┐
                 │  Provider → External API   │
                 └────────┬───────────────────┘
                          │
                          │ Response
                          ▼
                 ┌────────────────────────────┐
                 │  Process Response          │
                 └────────┬───────────────────┘
                          │
                          │ Return through layers
                          ▼
                 [Response flows back up]
                          │
                          │
                        ┌─▼────────────────┐
                        │  [RESPONSE OUT]  │
                        └──────────────────┘

═══════════════════════════════════════════════════════════════════════════
SUPPORTING SERVICES (Running Alongside)
═══════════════════════════════════════════════════════════════════════════

┌─────────────────────────────────────────────────────────────────────────┐
│                         LOGGING SERVICE                                 │
│                                                                         │
│  ILogger<T>                                                             │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  Layer 1 ──> Log: "Agent run started"                            │ │
│  │  Layer 2 ──> Log: "Authorization check passed"                   │ │
│  │  Layer 3 ──> Log: "Tool 'weather' invoked"                       │ │
│  │  Layer 4 ──> Log: "LLM call completed in 1.2s"                   │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                      MESSAGE STORAGE SERVICE                            │
│                                                                         │
│  ChatMessageStore                                                       │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  SaveAsync(thread, messages)                                      │ │
│  │  • Persist conversation history                                   │ │
│  │  • Support thread continuity                                      │ │
│  │  • Enable message retrieval                                       │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                    CHECKPOINT STORAGE SERVICE                           │
│                                                                         │
│  ICheckpointStore                                                       │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  SaveAsync(workflowId, state)                                     │ │
│  │  • Workflow state snapshots                                       │ │
│  │  • Resume capability                                              │ │
│  │  • Fault tolerance                                                │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────┐
│                      METRICS COLLECTION                                 │
│                                                                         │
│  OpenTelemetry Metrics                                                  │
│  ┌───────────────────────────────────────────────────────────────────┐ │
│  │  • agent.run.duration (histogram)                                 │ │
│  │  • agent.run.count (counter)                                      │ │
│  │  • tool.invocation.count (counter)                                │ │
│  │  • llm.tokens.used (counter)                                      │ │
│  └───────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘

═══════════════════════════════════════════════════════════════════════════
DATA FLOW TO SUPPORTING SERVICES
═══════════════════════════════════════════════════════════════════════════

Request Flow:                    Supporting Services:
                                
Layer 1 ─────────────────────┐   
  (Observability)             ├──> OpenTelemetry Collector
                              │    • Traces
                              │    • Metrics
Layer 2 ─────────────────────┤    • Logs
  (Middleware)                │   
                              │
Layer 3 ─────────────────────┤   
  (Function Handler)          ├──> Logger
                              │    • ILogger<T>
                              │    • Log levels
Layer 4 ─────────────────────┤    • Structured logging
  (Core Agent)                │   
                              │
                              ├──> Message Store
                              │    • Save messages
                              │    • Thread history
                              │   
                              ├──> Checkpoint Store
                              │    • Workflow state
                              │    • Resume points
                              │   
                              └──> Error Handler
                                   • Exception tracking
                                   • Retry policies

═══════════════════════════════════════════════════════════════════════════
CONFIGURATION EXAMPLE
═══════════════════════════════════════════════════════════════════════════

services
    // Observability
    .AddOpenTelemetry()
        .WithTracing(builder => builder
            .AddSource("Microsoft.Agents.AI")
            .AddConsoleExporter())
        .WithMetrics(builder => builder
            .AddMeter("Microsoft.Agents.AI")
            .AddConsoleExporter())
    
    // Logging
    .AddLogging(builder => builder
        .AddConsole()
        .SetMinimumLevel(LogLevel.Information))
    
    // Storage
    .AddSingleton<ChatMessageStore>()
    .AddSingleton<ICheckpointStore, FileCheckpointStore>()
    
    // Security
    .AddAuthentication()
    .AddAuthorization()
    
    // Agents with all concerns
    .AddAgent<MyAgent>();
```

---

## Component Interaction Summary

### Key Interaction Patterns

1. **Request/Response Pattern**: Used in basic agent execution
2. **Event Streaming Pattern**: Used in workflows and streaming responses
3. **Graph Execution Pattern**: Used in workflow orchestration
4. **Protocol Adapter Pattern**: Used in A2A and OpenAI hosting
5. **Middleware Chain Pattern**: Used in cross-cutting concerns
6. **Decorator Pattern**: Wrapping agents with observability and function handling
7. **Dependency Injection Pattern**: Resolving agents and dependencies at runtime

### Data Flow Characteristics

- **Synchronous**: Direct agent calls for simple use cases
- **Asynchronous**: All I/O operations use async/await
- **Streaming**: IAsyncEnumerable for real-time updates
- **Stateful**: State management in workflows and threads
- **Resilient**: Checkpoint/resume capability for long-running workflows

### Communication Mechanisms

- **In-Process**: Direct method calls within same process
- **HTTP/REST**: A2A protocol and OpenAI-compatible APIs
- **Event Streams**: Workflow events and streaming responses
- **Message Passing**: Between workflow executors and agents

### Component Responsibilities

| Component | Primary Responsibility | Key Operations |
|-----------|----------------------|----------------|
| **Application Layer** | User interface & application logic | Initiate requests, display results |
| **Hosting Layer** | Agent registration & discovery | DI registration, catalog lookup, HTTP endpoints |
| **Core Agent Layer** | Agent execution & coordination | Run agents, apply middleware, handle functions |
| **Workflow Layer** | Multi-agent orchestration | Graph execution, state management, routing |
| **Provider Layer** | LLM integration | API calls, response processing, protocol adaptation |
| **External SDK Layer** | Third-party service communication | HTTP requests, authentication, data formatting |

### Integration Points

1. **Startup**: Register agents, tools, and services in DI container
2. **Runtime**: Resolve agents from catalog, execute with dependencies
3. **Execution**: Flow through middleware, function handlers, and core logic
4. **Observation**: Emit traces, metrics, and logs throughout execution
5. **Storage**: Persist messages, state, and checkpoints for continuity

### Extension Points for Developers

- Implement custom agents by inheriting from `AIAgent`
- Create custom executors for workflow steps
- Add middleware via `DelegatingAIAgent`
- Implement custom storage with `ICheckpointStore` or `ChatMessageStore`
- Add tools that agents can invoke
- Create custom providers for new LLM services

---

**Document Type:** Component Interaction Diagrams (ASCII Art)  
**Generated:** October 16, 2025  
**Based on:** ARCHITECTURE.md v1.0  
**Format:** ASCII art for maximum compatibility (viewable in any text editor)

