"use client";

import { useState, type FormEvent } from "react";
import { api, ApiError } from "@/lib/api";
import type { Team } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";

interface TeamFormProps {
  team?: Team;
  onSaved: (team: Team) => void;
  onCancel: () => void;
}

export function TeamForm({ team, onSaved, onCancel }: TeamFormProps) {
  const [name, setName] = useState(team?.name ?? "");
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);
    try {
      const saved = team
        ? await api.patch<Team>(`/api/teams/${team.id}`, { name })
        : await api.post<Team>("/api/teams", { name });
      onSaved(saved);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save team.");
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-4">
      <Input
        label="Team name"
        value={name}
        onChange={(e) => setName(e.target.value)}
        required
        autoFocus
      />
      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{error}</p>}
      <div className="flex justify-end gap-2">
        <Button type="button" variant="secondary" onClick={onCancel}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isLoading}>
          {team ? "Save" : "Create"}
        </Button>
      </div>
    </form>
  );
}
