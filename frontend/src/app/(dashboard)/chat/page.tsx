"use client";

import { useEffect, useState } from "react";
import { ChatInterface } from "@/components/chat/ChatInterface";
import { api } from "@/lib/api";
import type { Team } from "@/lib/types";

export default function ChatPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null);

  useEffect(() => {
    api.get<Team[]>("/api/teams").then((t) => {
      setTeams(t);
      if (t.length > 0) setSelectedTeamId(t[0].id);
    });
  }, []);

  return (
    <div className="flex h-full flex-col">
      {teams.length > 1 && (
        <div className="flex items-center gap-2 border-b border-gray-200 bg-white px-6 py-2">
          <label htmlFor="team-select" className="text-xs text-gray-500">
            Team:
          </label>
          <select
            id="team-select"
            value={selectedTeamId ?? ""}
            onChange={(e) => setSelectedTeamId(Number(e.target.value))}
            className="rounded border border-gray-200 px-2 py-1 text-xs"
          >
            {teams.map((t) => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
      )}
      <div className="flex-1 overflow-hidden">
        <ChatInterface teamId={selectedTeamId} />
      </div>
    </div>
  );
}
