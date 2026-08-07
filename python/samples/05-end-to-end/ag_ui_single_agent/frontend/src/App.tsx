// Copyright (c) Microsoft. All rights reserved.

import { FormEvent, useEffect, useMemo, useRef, useState } from "react";

type AgUiEvent = Record<string, unknown> & { type: string };

interface ChatMessage {
  id: string;
  role: "assistant" | "user" | "system";
  text: string;
}

const BACKEND_URL = import.meta.env.VITE_BACKEND_URL ?? "http://127.0.0.1:8892";
const ENDPOINT = `${BACKEND_URL}/agent`;

const STARTER_PROMPTS = [
  "Explain the AG-UI protocol in two sentences.",
  "Give me three tips for writing clear commit messages.",
];

function randomId(): string {
  if (typeof crypto !== "undefined" && typeof crypto.randomUUID === "function") {
    return crypto.randomUUID();
  }
  return `id-${Math.random().toString(16).slice(2)}`;
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function safeParseJson(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return null;
  }
}

export default function App() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [draft, setDraft] = useState("");
  const [isRunning, setIsRunning] = useState(false);
  const [statusText, setStatusText] = useState("Ready");

  const threadIdRef = useRef<string>(randomId());
  const streamingMessageIdRef = useRef<string | null>(null);
  const transcriptRef = useRef<HTMLDivElement | null>(null);

  const canSend = useMemo(() => draft.trim().length > 0 && !isRunning, [draft, isRunning]);

  useEffect(() => {
    const node = transcriptRef.current;
    if (node) {
      node.scrollTop = node.scrollHeight;
    }
  }, [messages]);

  const pushMessage = (message: ChatMessage): void => {
    setMessages((prev) => [...prev, message]);
  };

  const appendToStreamingMessage = (messageId: string, delta: string): void => {
    setMessages((prev) => {
      const existing = prev.find((message) => message.id === messageId);
      if (existing) {
        return prev.map((message) =>
          message.id === messageId ? { ...message, text: `${message.text}${delta}` } : message,
        );
      }
      return [...prev, { id: messageId, role: "assistant", text: delta }];
    });
  };

  const handleEvent = (event: AgUiEvent): void => {
    switch (event.type) {
      case "RUN_STARTED":
        setStatusText("Thinking");
        break;
      case "TEXT_MESSAGE_START": {
        const messageId = typeof event.messageId === "string" ? event.messageId : randomId();
        streamingMessageIdRef.current = messageId;
        break;
      }
      case "TEXT_MESSAGE_CONTENT": {
        const messageId =
          typeof event.messageId === "string" ? event.messageId : streamingMessageIdRef.current ?? randomId();
        const delta = typeof event.delta === "string" ? event.delta : "";
        if (delta.length > 0) {
          setStatusText("Responding");
          appendToStreamingMessage(messageId, delta);
        }
        break;
      }
      case "TEXT_MESSAGE_END":
        streamingMessageIdRef.current = null;
        break;
      case "RUN_FINISHED":
        setStatusText("Ready");
        setIsRunning(false);
        break;
      case "RUN_ERROR": {
        const errorText = typeof event.message === "string" ? event.message : "The run failed.";
        pushMessage({ id: randomId(), role: "system", text: `Error: ${errorText}` });
        setStatusText("Error");
        setIsRunning(false);
        break;
      }
      default:
        break;
    }
  };

  const streamRun = async (body: Record<string, unknown>): Promise<void> => {
    const response = await fetch(ENDPOINT, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
    });

    if (!response.ok || !response.body) {
      throw new Error(`Request failed: ${response.status}`);
    }

    const reader = response.body.getReader();
    const decoder = new TextDecoder("utf-8");
    let buffer = "";

    const processSseChunk = (rawChunk: string): void => {
      const dataLines = rawChunk
        .split(/\r?\n/)
        .filter((line) => line.startsWith("data:"))
        .map((line) => line.slice(5).trim());

      if (dataLines.length === 0) {
        return;
      }

      const parsed = safeParseJson(dataLines.join("\n"));
      if (isObject(parsed) && typeof parsed.type === "string") {
        handleEvent(parsed as AgUiEvent);
      }
    };

    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        break;
      }

      buffer += decoder.decode(value, { stream: true });

      while (true) {
        const boundary = /\r?\n\r?\n/.exec(buffer);
        if (boundary === null) {
          break;
        }
        const boundaryIndex = boundary.index;
        const rawEvent = buffer.slice(0, boundaryIndex);
        buffer = buffer.slice(boundaryIndex + boundary[0].length);
        processSseChunk(rawEvent);
      }
    }

    const tail = buffer.trim();
    if (tail.length > 0) {
      processSseChunk(tail);
    }
  };

  const sendMessage = async (text: string): Promise<void> => {
    const trimmed = text.trim();
    if (trimmed.length === 0 || isRunning) {
      return;
    }

    pushMessage({ id: randomId(), role: "user", text: trimmed });
    setDraft("");
    setIsRunning(true);
    setStatusText("Connecting");
    streamingMessageIdRef.current = null;

    try {
      await streamRun({
        thread_id: threadIdRef.current,
        run_id: randomId(),
        messages: [{ role: "user", content: trimmed }],
      });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Unknown error";
      pushMessage({ id: randomId(), role: "system", text: `Network error: ${message}` });
      setStatusText("Network error");
      setIsRunning(false);
    }
  };

  const handleSubmit = (event: FormEvent<HTMLFormElement>): void => {
    event.preventDefault();
    void sendMessage(draft);
  };

  const startNewThread = (): void => {
    threadIdRef.current = randomId();
    streamingMessageIdRef.current = null;
    setMessages([]);
    setDraft("");
    setStatusText("Ready");
    setIsRunning(false);
  };

  return (
    <div className="page-shell">
      <header className="hero">
        <div>
          <p className="eyebrow">Agent Framework · AG-UI</p>
          <h1>Single Agent Chat</h1>
          <p className="subtitle">
            The simplest AG-UI integration: one chat agent with no tools and no context providers, streamed to a React
            client over Server-Sent Events.
          </p>
        </div>
        <div className="status-pill" data-running={isRunning}>
          <span>Status</span>
          <strong>{statusText}</strong>
        </div>
      </header>

      <main className="card chat-card">
        <div className="chat-toolbar">
          <h2>Conversation</h2>
          <button type="button" className="ghost-button" onClick={startNewThread} disabled={isRunning}>
            New Thread
          </button>
        </div>

        <div className="transcript" ref={transcriptRef}>
          {messages.length === 0 ? (
            <div className="empty-state">
              <p>Start the conversation with a prompt:</p>
              <div className="starter-prompts">
                {STARTER_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    type="button"
                    className="starter-prompt"
                    onClick={() => void sendMessage(prompt)}
                    disabled={isRunning}
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          ) : (
            messages.map((message) => (
              <div key={message.id} className={`bubble bubble-${message.role}`}>
                <span className="bubble-role">{message.role}</span>
                <p>{message.text}</p>
              </div>
            ))
          )}
        </div>

        <form className="composer" onSubmit={handleSubmit}>
          <input
            type="text"
            value={draft}
            placeholder="Send a message..."
            onChange={(event) => setDraft(event.target.value)}
            disabled={isRunning}
          />
          <button type="submit" className="send-button" disabled={!canSend}>
            Send
          </button>
        </form>
      </main>
    </div>
  );
}
