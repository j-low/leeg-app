// SSE streaming helper using fetch + ReadableStream.
// Uses fetch (not EventSource) so we can POST a body and send Authorization header.

import { getToken } from "./auth";
import type { ChatEvent } from "./types";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export async function* streamChat(
  input: string,
  context: Record<string, unknown>
): AsyncGenerator<ChatEvent> {
  const token = getToken();
  const response = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: JSON.stringify({ input, context }),
  });

  if (!response.ok || !response.body) {
    yield { type: "error", message: `HTTP ${response.status}: ${response.statusText}` };
    return;
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      buffer += decoder.decode(value, { stream: true });

      // SSE messages are separated by double newlines
      const parts = buffer.split("\n\n");
      buffer = parts.pop() ?? "";

      for (const part of parts) {
        const line = part.trim();
        if (!line.startsWith("data: ")) continue;
        const jsonStr = line.slice(6).trim();
        if (!jsonStr) continue;
        try {
          const event = JSON.parse(jsonStr) as ChatEvent;
          yield event;
          if (event.type === "done" || event.type === "error") return;
        } catch {
          // malformed JSON — skip
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}
