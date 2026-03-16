"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Game } from "@/lib/types";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { AttendanceGrid } from "@/components/games/AttendanceGrid";

export default function GamesPage() {
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    api.get<Game[]>("/api/games")
      .then((g) => setGames(g.sort((a, b) => a.date.localeCompare(b.date))))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="p-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Games</h1>

      {loading ? (
        <div className="flex justify-center py-12"><LoadingSpinner /></div>
      ) : games.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">No games scheduled.</p>
      ) : (
        <ul className="space-y-3">
          {games.map((game) => {
            const expanded = expandedId === game.id;
            const isPast = new Date(`${game.date}T${game.time}`) < new Date();

            return (
              <li key={game.id} className="rounded-lg border border-gray-200 bg-white shadow-sm">
                <button
                  className="flex w-full items-center justify-between px-4 py-3 text-left"
                  onClick={() => setExpandedId(expanded ? null : game.id)}
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-medium text-gray-900">
                        {new Date(game.date).toLocaleDateString("en-CA", {
                          weekday: "short",
                          month: "short",
                          day: "numeric",
                        })}
                      </span>
                      <span className="text-sm text-gray-500">{game.time}</span>
                      {isPast && (
                        <span className="rounded-full bg-gray-100 px-2 py-0.5 text-xs text-gray-400">
                          Past
                        </span>
                      )}
                    </div>
                    <p className="text-sm text-gray-500">{game.location}</p>
                    {game.notes && <p className="mt-0.5 text-xs text-gray-400">{game.notes}</p>}
                  </div>
                  <svg
                    className={`h-4 w-4 text-gray-400 transition-transform ${expanded ? "rotate-180" : ""}`}
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>

                {expanded && (
                  <div className="border-t border-gray-100 px-4 py-3">
                    <p className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">
                      Attendance
                    </p>
                    <AttendanceGrid gameId={game.id} />
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}
