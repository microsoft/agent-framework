# Task: TASK-206 Memory Context Provider

**Phase**: 3
**Priority**: High
**Estimated Effort**: 5 hours
**Dependencies**: TASK-012 (ContextProvider), TASK-204 (Context Provider Implementations)

### Objective
Implement advanced memory-based context provider that stores and retrieves conversation memories using vector search, enabling long-term memory and semantic recall for agents.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-9 (Context Providers) → Memory
- **Python Reference**: `agent-framework-mem0` package for mem0 integration
- **Mem0 Docs**: https://docs.mem0.ai/
- **Standards**: CLAUDE.md § Python Architecture → Context Providers

### Files to Create/Modify
- `src/context/memory-context-provider.ts` - Memory context provider with vector store
- `src/context/vector-store-interface.ts` - Vector store abstraction
- `src/context/__tests__/memory-context-provider.test.ts` - Unit tests

### Implementation Requirements

**Vector Store Interface**:
1. Define `VectorStore` interface for storage backends
2. Methods: `add()`, `search()`, `delete()`, `clear()`
3. Support embedding generation (via external service or local)
4. Return scored results with metadata

**Memory Context Provider**:
5. Accept VectorStore instance in constructor
6. On `invoked()`, extract important information from messages
7. Generate embeddings for memories
8. Store in vector store with metadata (timestamp, thread_id)
9. On `invoking()`, search vector store with query
10. Retrieve top-K relevant memories
11. Format as context instructions or messages
12. Support memory decay/TTL (optional)

**Memory Extraction**:
13. Extract facts, preferences, or key information from conversations
14. Use simple heuristics or LLM-based extraction
15. Filter duplicate or irrelevant memories

**Memory Retrieval**:
16. Generate query embedding from recent messages
17. Perform vector similarity search
18. Rank results by relevance score
19. Filter by minimum relevance threshold
20. Format results with context prompt template

**TypeScript Patterns**:
- Use dependency injection for vector store
- Use factory pattern for embedding services
- Type vector store interface strictly

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode

### Test Requirements
- [ ] Test memory storage after `invoked()`
- [ ] Test memory retrieval during `invoking()`
- [ ] Test vector search with embeddings
- [ ] Test memory formatting as Context
- [ ] Test memory filtering by relevance
- [ ] Test thread isolation (memories per thread)
- [ ] Test memory extraction from messages
- [ ] Test with mock vector store
- [ ] Test with real vector store (integration test)

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] MemoryContextProvider stores memories
- [ ] Memories retrieved via vector search
- [ ] Context formatted with relevant memories
- [ ] VectorStore interface defined
- [ ] Tests pass with >85% coverage
- [ ] TypeScript strict mode, ESLint passes
- [ ] JSDoc complete with examples

### Example Code Pattern
```typescript
export interface VectorStore {
  add(
    id: string,
    embedding: number[],
    metadata: Record<string, unknown>
  ): Promise<void>;

  search(
    query: number[],
    topK: number,
    filter?: Record<string, unknown>
  ): Promise<VectorSearchResult[]>;

  delete(id: string): Promise<void>;
  clear(): Promise<void>;
}

export interface VectorSearchResult {
  id: string;
  score: number;
  metadata: Record<string, unknown>;
  content?: string;
}

export class MemoryContextProvider extends ContextProvider {
  constructor(
    private readonly vectorStore: VectorStore,
    private readonly embeddingService: EmbeddingService,
    private readonly options: MemoryOptions = {}
  ) {
    super();
    this.topK = options.topK ?? 5;
    this.minRelevance = options.minRelevance ?? 0.7;
  }

  async invoking(messages: ChatMessage[]): Promise<Context> {
    if (messages.length === 0) {
      return new Context({});
    }

    // Generate query from recent messages
    const query = messages.slice(-3).map(m => m.text).join('\n');
    const queryEmbedding = await this.embeddingService.embed(query);

    // Search for relevant memories
    const results = await this.vectorStore.search(queryEmbedding, this.topK);

    // Filter by relevance
    const relevantMemories = results.filter(r => r.score >= this.minRelevance);

    if (relevantMemories.length === 0) {
      return new Context({});
    }

    // Format as instructions
    const memoriesText = relevantMemories
      .map(r => r.metadata.content)
      .join('\n\n');

    const instructions = `${ContextProvider.DEFAULT_CONTEXT_PROMPT}\n\n${memoriesText}`;

    return new Context({ instructions });
  }

  async invoked(
    requestMessages: ChatMessage[],
    responseMessages: ChatMessage[]
  ): Promise<void> {
    // Extract memories from conversation
    const memories = this.extractMemories(requestMessages, responseMessages);

    for (const memory of memories) {
      const embedding = await this.embeddingService.embed(memory.text);
      await this.vectorStore.add(memory.id, embedding, {
        content: memory.text,
        timestamp: Date.now(),
        threadId: memory.threadId
      });
    }
  }

  private extractMemories(
    requestMessages: ChatMessage[],
    responseMessages: ChatMessage[]
  ): Memory[] {
    const memories: Memory[] = [];

    // Simple extraction: store user messages as memories
    for (const msg of requestMessages) {
      if (msg.role === 'user' && msg.text) {
        memories.push({
          id: `${Date.now()}-${Math.random()}`,
          text: msg.text,
          threadId: this.getCurrentThreadId()
        });
      }
    }

    return memories;
  }
}

// Usage with in-memory vector store
class InMemoryVectorStore implements VectorStore {
  private vectors = new Map<string, { embedding: number[]; metadata: Record<string, unknown> }>();

  async add(id: string, embedding: number[], metadata: Record<string, unknown>): Promise<void> {
    this.vectors.set(id, { embedding, metadata });
  }

  async search(query: number[], topK: number): Promise<VectorSearchResult[]> {
    const results: VectorSearchResult[] = [];

    for (const [id, { embedding, metadata }] of this.vectors) {
      const score = this.cosineSimilarity(query, embedding);
      results.push({ id, score, metadata, content: metadata.content as string });
    }

    return results.sort((a, b) => b.score - a.score).slice(0, topK);
  }

  private cosineSimilarity(a: number[], b: number[]): number {
    // Calculate cosine similarity
    const dot = a.reduce((sum, val, i) => sum + val * b[i], 0);
    const magA = Math.sqrt(a.reduce((sum, val) => sum + val * val, 0));
    const magB = Math.sqrt(b.reduce((sum, val) => sum + val * val, 0));
    return dot / (magA * magB);
  }

  async delete(id: string): Promise<void> {
    this.vectors.delete(id);
  }

  async clear(): Promise<void> {
    this.vectors.clear();
  }
}

const vectorStore = new InMemoryVectorStore();
const embeddingService = new OpenAIEmbeddingService(apiKey);
const memoryProvider = new MemoryContextProvider(vectorStore, embeddingService);

const agent = new ChatAgent({
  chatClient: client,
  contextProviders: memoryProvider
});
```

### Related Tasks
- **Blocked by**: TASK-012 (ContextProvider), TASK-204 (Implementations)
- **Related**: TASK-205 (AggregateContextProvider can combine with memory)
