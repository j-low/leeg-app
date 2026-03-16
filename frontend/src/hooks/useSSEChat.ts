"use client";

import { useCallback, useRef, useState } from "react";
import { streamChat } from "@/lib/sse";
import type { ChatMessage, ToolCall } from "@/lib/types";

function uid(): string {
  return Math.random().toString(36).slice(2, 10);
}

export function useSSEChat(teamId: number | null) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const abortRef = useRef<boolean>(false);

  const sendMessage = useCallback(
    async (text: string) => {
      if (isStreaming) return;
      abortRef.current = false;

      // Append user message
      const userMsg: ChatMessage = { id: uid(), role: "user", text };
      // Append empty assistant placeholder
      const assistantId = uid();
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        text: "",
        isStreaming: true,
        toolCalls: [],
      };
      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      setIsStreaming(true);

      const context: Record<string, unknown> = {};
      if (teamId !== null) context.team_id = teamId;

      try {
        for await (const event of streamChat(text, context)) {
          if (abortRef.current) break;

          if (event.type === "answer_token") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId ? { ...m, text: m.text + event.text } : m
              )
            );
          } else if (event.type === "tool_start") {
            const tool: ToolCall = { name: event.name, done: false };
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, toolCalls: [...(m.toolCalls ?? []), tool] }
                  : m
              )
            );
          } else if (event.type === "tool_result") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      toolCalls: (m.toolCalls ?? []).map((t) =>
                        t.name === event.name ? { ...t, done: true } : t
                      ),
                    }
                  : m
              )
            );
          } else if (event.type === "done") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? { ...m, text: event.text_for_user, isStreaming: false }
                  : m
              )
            );
          } else if (event.type === "error") {
            setMessages((prev) =>
              prev.map((m) =>
                m.id === assistantId
                  ? {
                      ...m,
                      text: event.message,
                      isStreaming: false,
                      isError: true,
                    }
                  : m
              )
            );
          }
          // ping — ignore
        }
      } catch {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? {
                  ...m,
                  text: "Something went wrong. Please try again.",
                  isStreaming: false,
                  isError: true,
                }
              : m
          )
        );
      } finally {
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, isStreaming: false } : m
          )
        );
        setIsStreaming(false);
      }
    },
    [isStreaming, teamId]
  );

  const clearMessages = useCallback(() => {
    abortRef.current = true;
    setMessages([]);
    setIsStreaming(false);
  }, []);

  return { messages, isStreaming, sendMessage, clearMessages };
}
