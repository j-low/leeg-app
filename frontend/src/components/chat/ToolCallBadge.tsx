import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import type { ToolCall } from "@/lib/types";

export function ToolCallBadge({ tool }: { tool: ToolCall }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-gray-200 bg-gray-50 px-2.5 py-1 text-xs text-gray-600">
      {tool.done ? (
        <svg className="h-3 w-3 text-green-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
        </svg>
      ) : (
        <LoadingSpinner size="sm" className="h-3 w-3 text-blue-500" />
      )}
      {tool.name.replace(/_/g, " ")}
    </span>
  );
}
