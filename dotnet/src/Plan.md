# Introduction

AG-UI is a lightweight, event-based protocol that standardizes communication between AI agents and user-facing applications, enabling real-time, multimodal, and interactive experiences.

The Agent–User Interaction (AG-UI) Protocol is designed to simplify and streamline how AI agents integrate with frontend applications. It provides a unified framework for transmitting agent state, user intents, and interaction events, allowing developers to build responsive, reliable, and user-friendly agentic features without complex custom wiring

## Goals 
* We are planning to support AG-UI inside Microsoft Agent Framework.
* We will focus our implementation in .NET as a first step.

## Architecture

Our support for AG-UI will be structured in two separate libraries:

### Client

Microsoft.Agents.AI.AGUI will provide support for communicating with any standard AG-UI compliant server. In particular with our
AG-UI Server.

We will follow a pattern similar of that of Microsoft.Agents.AI.A2A, where we will expose an AGUIAgent extending AIAgent that will
manage the conversation thread and runs.

The client code will be responsible for:
* Creating an agent instance (name, id, description)
* Converting the list of AG-UI messages into the equivalent Microsoft.Extensions.AI messages
* Keeping track of the message thread
* Reacting to server response updates and building up new messages while delivering updates to the client

### Server

Microsoft.Agents.AI.Hosting.AGUI.AspNetCore will provide support for exposing an existing ChatClientAgent as an AG-UI agent that will
be responsible for:
* Consuming AG-UI compliant inputs.
* Mapping those inputs into Microsoft.Extensions.AI abstractions.
* Invoking the underlying agent and producing a standard set of AG-UI events as a response.

We will have a MapAGUIAgent method that we will use to map the agent as an AG-UI agent.

### Principles

All the AG-UI types will be internal. In fact, we will not have an AG-UI library at all and we will instead share the types as source code between the client and
server. We will place that code inside the `Microsoft.Agents.AI.AGUI` library under a `Shared` and the hosting project will reference it as `Compile Include="<<relative-path-to-shared>>" LinkBase="Shared"`.

We will only expose public API that is part of Microsoft.Extensions.AI, Microsoft.Extensions.AgentFramework or .NET framework (including ASP.NET Core)

## Testing

* We will have a Microsoft.Agents.AI.AGUI.UnitTests project that will contain the unit tests for the client.
* We will have a Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests project that will contain the unit tests for the server.
* We will have a Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests project that will tests the client and the server
  together using WebApplicationFactory.

## Implementation plan

* Infrastructure Setup - Create Required Projects and setup dependencies
  * `Microsoft.Agents.AI.AGUI` (client library)
  * `Microsoft.Agents.AI.Hosting.AGUI.AspNetCore` (server library)
  * `Microsoft.Agents.AI.AGUI.UnitTests`
  * `Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.UnitTests`  
  * `Microsoft.Agents.AI.Hosting.AGUI.AspNetCore.IntegrationTests`

* Implement basic agentic chat
  * The scenario is as follows:
    * Create a new instance of AGUIClient instance.
    * Create a new thread and send a message to the server.
    * The server should reply to the client a stream of text events
    * The client will consume those events.
    * The client will contain an updated conversation at the end of
      the interaction.    

### Implementation constraints

* For each scenario, we will define the minimum number of types and members needed to implement that scenario. For example, we won't define additional message types or events if they are not used.

* For testing, we will focus on testing public methods where possible.
  * We will not test constructors.
  * We will not test auto properties.
  * We will not test any method that is indirectly used in the test of
    another method.
* We will not use reflection to test any private method directly.
* We will give InternalsVisibleTo access to test projects if needed for testing purposes.
* If we want to test a private method, we might mark it as `internal` and add the
  following comment above it `// For testing purposes only`.

* We will be using Behavior Driven Development for implementing each scenario.
  * First we will define an integration test using web application factory to validate the scenario.
  * We will then define the types and members that are needed to support that scenario.
  * Then for each member that we want to test, we will write the unit test, run it, see the test fail, implement the functionality, run the test, and iterate until we make the test pass.
  * Once we have unit tests for all the individual members we care testing, we will run our integration tests to validate everything works.