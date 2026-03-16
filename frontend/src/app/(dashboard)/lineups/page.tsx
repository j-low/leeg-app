"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Game, Lineup, Team } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { LineupView } from "@/components/lineups/LineupView";

export default function LineupsPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [lineups, setLineups] = useState<Lineup[]>([]);
  const [loading, setLoading] = useState(true);
  const [suggestingGameId, setSuggestingGameId] = useState<number | null>(null);
  const [expandedId, setExpandedId] = useState<number | null>(null);

  useEffect(() => {
    Promise.all([
      api.get<Team[]>("/api/teams"),
      api.get<Game[]>("/api/games"),
      api.get<Lineup[]>("/api/lineups"),
    ])
      .then(([t, g, l]) => {
        setTeams(t);
        setGames(g);
        setLineups(l.sort((a, b) => b.id - a.id));
      })
      .finally(() => setLoading(false));
  }, []);

  const handleSuggest = async (gameId: number) => {
    setSuggestingGameId(gameId);
    try {
      const lineup = await api.post<Lineup>("/api/lineups/suggest", { game_id: gameId });
      setLineups((prev) => [lineup, ...prev]);
      setExpandedId(lineup.id);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Failed to generate lineup.");
    } finally {
      setSuggestingGameId(null);
    }
  };

  const getGameLabel = (gameId: number) => {
    const game = games.find((g) => g.id === gameId);
    if (!game) return `Game #${gameId}`;
    return `${game.date} · ${game.time} · ${game.location}`;
  };

  const upcomingGames = games.filter((g) => new Date(`${g.date}T${g.time}`) > new Date());

  return (
    <div className="p-8">
      <h1 className="mb-6 text-2xl font-bold text-gray-900">Lineups</h1>

      {loading ? (
        <div className="flex justify-center py-12"><LoadingSpinner /></div>
      ) : (
        <>
          {upcomingGames.length > 0 && (
            <section className="mb-8">
              <h2 className="mb-3 text-sm font-semibold text-gray-700">Suggest a lineup</h2>
              <div className="space-y-2">
                {upcomingGames.map((game) => (
                  <div key={game.id} className="flex items-center justify-between rounded-lg border border-gray-200 bg-white px-4 py-3 shadow-sm">
                    <div>
                      <p className="text-sm font-medium text-gray-900">
                        {new Date(game.date).toLocaleDateString("en-CA", {
                          weekday: "short", month: "short", day: "numeric",
                        })}
                        {" · "}{game.time}
                      </p>
                      <p className="text-xs text-gray-500">{game.location}</p>
                    </div>
                    <Button
                      onClick={() => handleSuggest(game.id)}
                      isLoading={suggestingGameId === game.id}
                    >
                      Suggest lineup
                    </Button>
                  </div>
                ))}
              </div>
            </section>
          )}

          <section>
            <h2 className="mb-3 text-sm font-semibold text-gray-700">Past lineups</h2>
            {lineups.length === 0 ? (
              <p className="py-8 text-center text-sm text-gray-400">No lineups yet.</p>
            ) : (
              <ul className="space-y-3">
                {lineups.map((lineup) => (
                  <li key={lineup.id} className="rounded-lg border border-gray-200 bg-white shadow-sm">
                    <button
                      className="flex w-full items-center justify-between px-4 py-3 text-left"
                      onClick={() => setExpandedId(expandedId === lineup.id ? null : lineup.id)}
                    >
                      <div>
                        <p className="text-sm font-medium text-gray-900">
                          {getGameLabel(lineup.game_id)}
                        </p>
                        <p className="text-xs text-gray-400">
                          Generated {new Date(lineup.created_at).toLocaleString()}
                        </p>
                        {lineup.criteria && (
                          <p className="text-xs text-gray-500 mt-0.5">{lineup.criteria}</p>
                        )}
                      </div>
                      <svg
                        className={`h-4 w-4 text-gray-400 transition-transform ${expandedId === lineup.id ? "rotate-180" : ""}`}
                        fill="none" stroke="currentColor" viewBox="0 0 24 24"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    {expandedId === lineup.id && (
                      <div className="border-t border-gray-100 px-4 py-4">
                        <LineupView lineup={lineup} />
                      </div>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </section>
        </>
      )}
    </div>
  );
}
