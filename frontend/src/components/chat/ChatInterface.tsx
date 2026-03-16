"use client";

import { useEffect, useRef, useState, type KeyboardEvent } from "react";
import { useSSEChat } from "@/hooks/useSSEChat";
import { ChatMessage } from "./ChatMessage";
import { Button } from "@/components/ui/Button";

interface ChatInterfaceProps {
  teamId: number | null;
}

export function ChatInterface({ teamId }: ChatInterfaceProps) {
  const { messages, isStreaming, sendMessage, clearMessages } = useSSEChat(teamId);
  const [input, setInput] = useState("");
  const bottomRef = useRef<HTMLDivElement>(null);

  // Auto-scroll on new messages/tokens
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    await sendMessage(text);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex h-full flex-col">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-gray-200 bg-white px-6 py-3">
        <div>
          <h1 className="text-base font-semibold text-gray-900">AI Chat</h1>
          <p className="text-xs text-gray-500">Ask anything about your team in plain English</p>
        </div>
        {messages.length > 0 && (
          <button
            onClick={clearMessages}
            className="text-xs text-gray-400 hover:text-gray-600"
          >
            Clear
          </button>
        )}
      </div>

      {/* Message list */}
      <div className="flex-1 overflow-y-auto px-6 py-4">
        {messages.length === 0 ? (
          <div className="flex h-full flex-col items-center justify-center text-center">
            <div className="mb-3 text-4xl">🏒</div>
            <p className="text-sm font-medium text-gray-700">Ask anything about your team</p>
            <div className="mt-4 flex flex-col gap-2">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => sendMessage(s)}
                  className="rounded-lg border border-gray-200 bg-white px-4 py-2 text-left text-sm text-gray-600 hover:bg-gray-50 hover:border-blue-300 transition-colors"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <div className="space-y-4">
            {messages.map((msg) => (
              <ChatMessage key={msg.id} message={msg} />
            ))}
            <div ref={bottomRef} />
          </div>
        )}
      </div>

      {/* Input */}
      <div className="border-t border-gray-200 bg-white p-4">
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask about your roster, games, attendance…"
            rows={1}
            disabled={isStreaming}
            className="flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm outline-none transition-colors focus:border-blue-500 focus:ring-1 focus:ring-blue-500 disabled:bg-gray-50"
          />
          <Button onClick={handleSend} disabled={!input.trim() || isStreaming} isLoading={isStreaming}>
            Send
          </Button>
        </div>
        <p className="mt-1.5 text-xs text-gray-400">Enter to send · Shift+Enter for new line</p>
      </div>
    </div>
  );
}

const SUGGESTIONS = [
  "Who's on my roster?",
  "When is the next game?",
  "Which players haven't confirmed attendance?",
  "Suggest a balanced lineup for the next game",
];
