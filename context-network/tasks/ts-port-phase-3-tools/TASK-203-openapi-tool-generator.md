# Task: TASK-203 OpenAPI Tool Generator

**Phase**: 3
**Priority**: High
**Estimated Effort**: 7 hours
**Dependencies**: TASK-005 (Tool System)

### Objective
Implement OpenAPI specification parser that automatically generates AIFunction tools from OpenAPI/Swagger specs, enabling agents to call REST APIs without manual function definition.

### Context References
- **Spec Section**: 002-typescript-feature-parity.md § FR-7 (Tools) → OpenAPI Support
- **Python Reference**: Python implementation may use external libraries (openapi-core, etc.)
- **.NET Reference**: `/dotnet/src/Microsoft.Agents.AI/Tools/OpenAPI/` - OpenAPI tool generation
- **OpenAPI Spec**: https://spec.openapis.org/oas/v3.1.0

### Files to Create/Modify
- `src/tools/openapi-tool-generator.ts` - OpenAPI parser and tool generator
- `src/tools/openapi-tool.ts` - OpenAPITool class
- `src/tools/__tests__/openapi-tool-generator.test.ts` - Unit tests

### Implementation Requirements

**OpenAPI Parsing**:
1. Parse OpenAPI 3.x JSON/YAML specifications
2. Extract operations (GET, POST, PUT, DELETE, etc.)
3. Parse operation parameters (path, query, header, body)
4. Parse request body schemas
5. Parse response schemas
6. Extract security requirements

**Tool Generation**:
7. Generate one AIFunction per OpenAPI operation
8. Convert operation ID to function name (or generate from path+method)
9. Use operation summary/description for function description
10. Convert parameters to Pydantic input model
11. Handle required vs optional parameters
12. Support nested object parameters

**HTTP Execution**:
13. Implement HTTP client wrapper
14. Build URL from base URL + path + path parameters
15. Add query parameters to URL
16. Add headers (including auth headers)
17. Serialize request body to JSON
18. Execute HTTP request
19. Parse response and extract result
20. Handle HTTP errors (4xx, 5xx)

**Authentication**:
21. Support API key authentication (header or query)
22. Support Bearer token authentication
23. Support Basic authentication
24. Support OAuth2 (optional, advanced)

**TypeScript Patterns**:
- Use axios or fetch for HTTP
- Type OpenAPI spec with TypeScript interfaces
- Generate strict types for parameters

**Code Standards**:
- 120 character line length
- JSDoc with examples
- Strict mode

### Test Requirements
- [ ] Test parsing OpenAPI 3.0 spec
- [ ] Test parsing OpenAPI 3.1 spec
- [ ] Test generating AIFunctions from operations
- [ ] Test parameter conversion to Pydantic models
- [ ] Test required vs optional parameters
- [ ] Test path parameter substitution
- [ ] Test query parameter serialization
- [ ] Test request body serialization
- [ ] Test response parsing
- [ ] Test API key authentication
- [ ] Test Bearer token authentication
- [ ] Test HTTP error handling

**Minimum Coverage**: 85%

### Acceptance Criteria
- [ ] Parse OpenAPI 3.x specifications
- [ ] Generate AIFunctions for all operations
- [ ] Execute HTTP requests correctly
- [ ] Handle authentication methods
- [ ] Error handling for HTTP and parsing errors
- [ ] Tests pass with >85% coverage
- [ ] TypeScript strict mode, ESLint passes

### Example Code Pattern
```typescript
export class OpenAPIToolGenerator {
  static async fromSpec(
    spec: OpenAPISpec | string,
    options?: OpenAPIToolOptions
  ): Promise<AIFunction[]> {
    const parsedSpec = typeof spec === 'string'
      ? await this.parseSpec(spec)
      : spec;

    const tools: AIFunction[] = [];

    for (const [path, pathItem] of Object.entries(parsedSpec.paths)) {
      for (const [method, operation] of Object.entries(pathItem)) {
        if (!isOperation(operation)) continue;

        const tool = this.createToolFromOperation(
          parsedSpec,
          path,
          method,
          operation,
          options
        );
        tools.push(tool);
      }
    }

    return tools;
  }

  private static createToolFromOperation(
    spec: OpenAPISpec,
    path: string,
    method: string,
    operation: Operation,
    options?: OpenAPIToolOptions
  ): AIFunction {
    const name = operation.operationId || `${method}_${path.replace(/[^a-zA-Z0-9]/g, '_')}`;
    const description = operation.summary || operation.description || '';

    // Build parameter model
    const parameters = this.extractParameters(operation);
    const inputModel = this.createInputModel(name, parameters);

    // Create execution function
    const executionFunc = async (args: any) => {
      const url = this.buildURL(spec.servers[0].url, path, args);
      const headers = this.buildHeaders(args, options?.auth);
      const body = this.buildBody(args, operation.requestBody);

      const response = await fetch(url, {
        method: method.toUpperCase(),
        headers,
        body: body ? JSON.stringify(body) : undefined
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      return await response.json();
    };

    return new AIFunction({
      name,
      description,
      inputModel,
      func: executionFunc
    });
  }

  private static extractParameters(operation: Operation): Parameter[] {
    const params: Parameter[] = [];

    // Path parameters
    if (operation.parameters) {
      params.push(...operation.parameters);
    }

    // Request body parameters
    if (operation.requestBody) {
      const schema = operation.requestBody.content['application/json']?.schema;
      if (schema && schema.properties) {
        for (const [name, prop] of Object.entries(schema.properties)) {
          params.push({
            name,
            in: 'body',
            required: schema.required?.includes(name) ?? false,
            schema: prop
          });
        }
      }
    }

    return params;
  }
}

// Usage
const tools = await OpenAPIToolGenerator.fromSpec('https://api.example.com/openapi.json', {
  auth: { type: 'bearer', token: 'secret-token' }
});

const agent = new ChatAgent({
  chatClient: client,
  tools
});
```

### Related Tasks
- **Blocked by**: TASK-005 (Tool System)
- **Related**: TASK-201 (Tool Execution)
