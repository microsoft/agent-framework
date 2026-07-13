# Agent Framework Retrieval Augmented Generation (RAG)

These samples show how to create an agent with the Agent Framework that uses Memory to remember previous conversations or facts from previous conversations.

|Sample|Description|
|---|---|
|[Chat History memory](./AgentWithMemory_Step01_ChatHistoryMemory/)|This sample demonstrates how to enable an agent to remember messages from previous conversations.|
|[Memory with MemoryStore](./AgentWithMemory_Step02_MemoryUsingMem0/)|This sample demonstrates how to create and run an agent that uses the Mem0 service to extract and retrieve individual memories.|
|[Custom Memory Implementation](../../01-get-started/04_memory/)|This sample demonstrates how to create a custom memory component and attach it to an agent.|
|[Memory with Microsoft Foundry](./AgentWithMemory_Step04_MemoryUsingFoundry/)|This sample demonstrates how to create and run an agent that uses Microsoft Foundry's managed memory service to extract and retrieve individual memories.|
|[Bounded Chat History with Overflow](./AgentWithMemory_Step05_BoundedChatHistory/)|This sample demonstrates how to create a bounded chat history provider that overflows older messages to a vector store and recalls them as memories.|

> **See also**: [Memory Search with Foundry Agents](../AgentProviders/foundry/Agent_Step22_MemorySearch/) - demonstrates using the built-in Memory Search tool with Microsoft Foundry agents.
>
> **See also**: [Neo4j Shopping Assistant](../../../../neo4j-shopping-assistant-sample/) - a retail assistant that uses [`AgentMemory`](https://www.nuget.org/packages/AgentMemory), the .NET Neo4j memory provider, via its `Neo4jMemoryContextProvider` (`AIContextProvider`). Ships as a **standalone** sample consuming the published NuGet packages (targets `Microsoft.Agents.AI` 1.9.0), so it lives outside this build/CPM tree rather than as a project reference here.

