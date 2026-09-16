import { describe, expect, it } from "vitest";

import { MiddlewareFailure, ToolExecutionError, defineTool, functionCall } from "../src/index.js";

const parameters = {
  type: "object",
  properties: { value: { type: "number" } },
  required: ["value"],
  additionalProperties: false,
};

describe("FunctionTool", () => {
  it("parses and validates model arguments before invoking", async () => {
    const tool = defineTool({
      name: "double",
      description: "Double a number.",
      parameters,
      execute: ({ value }) => (value as number) * 2,
    });

    await expect(tool.invoke(functionCall("call-1", "double", '{"value":4}'))).resolves.toBe(8);
    await expect(tool.invoke(functionCall("call-2", "double", '{"value":"four"}'))).rejects.toThrow(ToolExecutionError);
  });

  it("runs middleware in onion order and permits argument mutation", async () => {
    const events: string[] = [];
    const tool = defineTool({
      name: "double",
      parameters,
      middleware: [
        async (context, next) => {
          events.push("first:before");
          context.arguments.value = (context.arguments.value as number) + 1;
          await next();
          events.push("first:after");
        },
        async (_context, next) => {
          events.push("second:before");
          await next();
          events.push("second:after");
        },
      ],
      execute: ({ value }) => {
        events.push("tool");
        return (value as number) * 2;
      },
    });

    await expect(tool.invoke(functionCall("call-1", "double", { value: 4 }))).resolves.toBe(10);
    expect(events).toEqual(["first:before", "second:before", "tool", "second:after", "first:after"]);
  });

  it("preserves fatal middleware failures", async () => {
    const tool = defineTool({
      name: "double",
      parameters,
      middleware: [async () => Promise.reject(new MiddlewareFailure("stop"))],
      execute: ({ value }) => value,
    });

    await expect(tool.invoke(functionCall("call-1", "double", { value: 4 }))).rejects.toThrow(MiddlewareFailure);
  });

  it("keeps trusted runtime arguments separate from model arguments", async () => {
    const tool = defineTool({
      name: "lookup",
      parameters: {
        type: "object",
        properties: { tenantId: { type: "string" } },
        required: ["tenantId"],
        additionalProperties: false,
      },
      execute: ({ tenantId }, context) => ({
        modelTenantId: tenantId,
        runtimeTenantId: context.runtimeArguments.tenantId,
      }),
    });

    await expect(
      tool.invoke(functionCall("call-1", "lookup", { tenantId: "model-controlled" }), {
        runtimeArguments: { tenantId: "trusted-host" },
      }),
    ).resolves.toEqual({ modelTenantId: "model-controlled", runtimeTenantId: "trusted-host" });
  });

  it("counts failed executions toward the invocation limit", async () => {
    let executions = 0;
    const tool = defineTool({
      name: "fail",
      parameters: { type: "object", additionalProperties: false },
      maxInvocations: 1,
      execute: () => {
        executions += 1;
        throw new Error("failed");
      },
    });

    await expect(tool.invoke(functionCall("call-1", "fail"))).rejects.toThrow("failed");
    await expect(tool.invoke(functionCall("call-2", "fail"))).rejects.toThrow("invocation limit");
    expect(executions).toBe(1);
  });

  it("revalidates arguments after middleware mutation", async () => {
    let executed = false;
    const tool = defineTool({
      name: "double",
      parameters,
      middleware: [
        async (context, next) => {
          context.arguments.value = "not a number";
          await next();
        },
      ],
      execute: () => {
        executed = true;
      },
    });

    await expect(tool.invoke(functionCall("call-1", "double", { value: 4 }))).rejects.toThrow(ToolExecutionError);
    expect(executed).toBe(false);
  });

  it.each([0, 1.5, Number.NaN, Number.POSITIVE_INFINITY])("rejects invalid invocation limit %s", (limit) => {
    expect(() =>
      defineTool({
        name: "limited",
        parameters,
        maxInvocations: limit,
        execute: () => undefined,
      }),
    ).toThrow(RangeError);
  });

  it("counts argument validation failures toward the invocation error limit", async () => {
    const tool = defineTool({
      name: "double",
      parameters,
      maxInvocationErrors: 1,
      execute: ({ value }) => value,
    });

    await expect(tool.invoke(functionCall("call-1", "double", { value: "invalid" }))).rejects.toThrow(
      ToolExecutionError,
    );
    await expect(tool.invoke(functionCall("call-2", "double", { value: 2 }))).rejects.toThrow("invocation error limit");
  });
});
