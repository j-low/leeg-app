"use client";

import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import type { Player } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

const POSITIONS = ["Forward", "Defense", "Goalie"];

interface PlayerFormProps {
  teamId: number;
  player?: Player;
  onSaved: (player: Player) => void;
  onCancel: () => void;
}

export function PlayerForm({ teamId, player, onSaved, onCancel }: PlayerFormProps) {
  const [name, setName] = useState(player?.name ?? "");
  const [phone, setPhone] = useState(player?.phone ?? "");
  const [positions, setPositions] = useState<string[]>(player?.position_prefs ?? []);
  const [subFlag, setSubFlag] = useState(player?.sub_flag ?? false);
  const [skillNotes, setSkillNotes] = useState(player?.skill_notes ?? "");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const togglePosition = (pos: string) =>
    setPositions((prev) =>
      prev.includes(pos) ? prev.filter((p) => p !== pos) : [...prev, pos]
    );

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const payload = {
        name,
        phone,
        team_id: teamId,
        position_prefs: positions,
        sub_flag: subFlag,
        skill_notes: skillNotes || null,
      };
      const saved = player
        ? await api.patch<Player>(`/api/players/${player.id}`, payload)
        : await api.post<Player>("/api/players", payload);
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save player.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Input label="Name" value={name} onChange={(e) => setName(e.target.value)} required autoFocus />
      <Input label="Phone" type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} required />

      <div>
        <p className="mb-1.5 text-sm font-medium text-gray-700">Position preferences</p>
        <div className="flex gap-2">
          {POSITIONS.map((pos) => (
            <button
              key={pos}
              type="button"
              onClick={() => togglePosition(pos)}
              className={`rounded-full border px-3 py-1 text-xs font-medium transition-colors ${
                positions.includes(pos)
                  ? "border-blue-500 bg-blue-50 text-blue-700"
                  : "border-gray-300 bg-white text-gray-600 hover:bg-gray-50"
              }`}
            >
              {pos}
            </button>
          ))}
        </div>
      </div>

      <label className="flex items-center gap-2 text-sm">
        <input
          type="checkbox"
          checked={subFlag}
          onChange={(e) => setSubFlag(e.target.checked)}
          className="rounded"
        />
        <span className="text-gray-700">Available as sub</span>
      </label>

      <div className="flex flex-col gap-1">
        <label className="text-sm font-medium text-gray-700">Skill notes</label>
        <textarea
          value={skillNotes}
          onChange={(e) => setSkillNotes(e.target.value)}
          rows={2}
          className="rounded-md border border-gray-300 px-3 py-2 text-sm outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500"
          placeholder="Optional notes…"
        />
      </div>

      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}

      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" isLoading={isLoading}>{player ? "Save" : "Add player"}</Button>
      </div>
    </form>
  );
}
