"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Team, Player } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { PlayerForm } from "@/components/roster/PlayerForm";

export default function RosterPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null);
  const [players, setPlayers] = useState<Player[]>([]);
  const [loadingTeams, setLoadingTeams] = useState(true);
  const [loadingPlayers, setLoadingPlayers] = useState(false);
  const [showAdd, setShowAdd] = useState(false);
  const [editPlayer, setEditPlayer] = useState<Player | null>(null);

  useEffect(() => {
    api.get<Team[]>("/api/teams").then((t) => {
      setTeams(t);
      if (t.length > 0) setSelectedTeamId(t[0].id);
      setLoadingTeams(false);
    });
  }, []);

  useEffect(() => {
    if (!selectedTeamId) return;
    setLoadingPlayers(true);
    api
      .get<Player[]>(`/api/teams/${selectedTeamId}/players`)
      .then(setPlayers)
      .finally(() => setLoadingPlayers(false));
  }, [selectedTeamId]);

  const handleSaved = (player: Player) => {
    setPlayers((prev) =>
      prev.some((p) => p.id === player.id)
        ? prev.map((p) => (p.id === player.id ? player : p))
        : [...prev, player]
    );
    setShowAdd(false);
    setEditPlayer(null);
  };

  const handleDelete = async (player: Player) => {
    if (!confirm(`Remove ${player.name} from the roster?`)) return;
    try {
      await api.delete(`/api/players/${player.id}`);
      setPlayers((prev) => prev.filter((p) => p.id !== player.id));
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Failed to delete player.");
    }
  };

  return (
    <div className="p-8">
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold text-gray-900">Roster</h1>
        <div className="flex items-center gap-3">
          {teams.length > 1 && (
            <select
              value={selectedTeamId ?? ""}
              onChange={(e) => setSelectedTeamId(Number(e.target.value))}
              className="rounded-md border border-gray-300 px-2 py-1.5 text-sm"
            >
              {teams.map((t) => (
                <option key={t.id} value={t.id}>{t.name}</option>
              ))}
            </select>
          )}
          {selectedTeamId && (
            <Button onClick={() => setShowAdd(true)}>Add player</Button>
          )}
        </div>
      </div>

      {loadingTeams || loadingPlayers ? (
        <div className="flex justify-center py-12"><LoadingSpinner /></div>
      ) : players.length === 0 ? (
        <p className="py-8 text-center text-sm text-gray-400">
          No players yet. Add one to get started.
        </p>
      ) : (
        <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
          {players.map((player) => (
            <li key={player.id} className="flex items-center justify-between px-4 py-3">
              <div>
                <p className="font-medium text-gray-900">{player.name}</p>
                <div className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-gray-500">
                  <span>{player.phone}</span>
                  {player.position_prefs.length > 0 && (
                    <span className="rounded-full bg-gray-100 px-2 py-0.5">
                      {player.position_prefs.join(", ")}
                    </span>
                  )}
                  {player.sub_flag && (
                    <span className="rounded-full bg-yellow-50 px-2 py-0.5 text-yellow-700 border border-yellow-200">
                      Sub
                    </span>
                  )}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <Button variant="secondary" onClick={() => setEditPlayer(player)}>Edit</Button>
                <Button variant="danger" onClick={() => handleDelete(player)}>Remove</Button>
              </div>
            </li>
          ))}
        </ul>
      )}

      <Modal open={showAdd} onClose={() => setShowAdd(false)} title="Add player">
        {selectedTeamId && (
          <PlayerForm
            teamId={selectedTeamId}
            onSaved={handleSaved}
            onCancel={() => setShowAdd(false)}
          />
        )}
      </Modal>

      <Modal open={!!editPlayer} onClose={() => setEditPlayer(null)} title="Edit player">
        {editPlayer && selectedTeamId && (
          <PlayerForm
            teamId={selectedTeamId}
            player={editPlayer}
            onSaved={handleSaved}
            onCancel={() => setEditPlayer(null)}
          />
        )}
      </Modal>
    </div>
  );
}
