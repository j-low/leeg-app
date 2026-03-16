import type { ChatMessage as ChatMessageType } from "@/lib/types";
import { ToolCallBadge } from "./ToolCallBadge";

export function ChatMessage({ message }: { message: ChatMessageType }) {
  const isUser = message.role === "user";

  return (
    <div className={`flex gap-3 ${isUser ? "flex-row-reverse" : "flex-row"}`}>
      <div
        className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-xs font-semibold ${
          isUser ? "bg-blue-600 text-white" : "bg-gray-200 text-gray-600"
        }`}
      >
        {isUser ? "Y" : "AI"}
      </div>

      <div className={`max-w-[80%] space-y-1.5 ${isUser ? "items-end" : "items-start"} flex flex-col`}>
        {/* Tool call badges */}
        {message.toolCalls && message.toolCalls.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.toolCalls.map((tool) => (
              <ToolCallBadge key={tool.name} tool={tool} />
            ))}
          </div>
        )}

        {/* Message bubble */}
        {(message.text || message.isStreaming) && (
          <div
            className={`rounded-2xl px-4 py-2.5 text-sm leading-relaxed ${
              isUser
                ? "bg-blue-600 text-white"
                : message.isError
                ? "bg-red-50 text-red-700 border border-red-200"
                : "bg-white text-gray-800 border border-gray-200 shadow-sm"
            }`}
          >
            <span style={{ whiteSpace: "pre-wrap" }}>{message.text}</span>
            {message.isStreaming && !message.text && (
              <span className="inline-block h-4 w-1 animate-pulse bg-current ml-0.5" />
            )}
            {message.isStreaming && message.text && (
              <span className="inline-block h-4 w-0.5 animate-pulse bg-current ml-0.5" />
            )}
          </div>
        )}
      </div>
    </div>
  );
}
