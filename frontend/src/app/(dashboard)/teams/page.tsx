"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { Team } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";
import { TeamList } from "@/components/teams/TeamList";
import { TeamForm } from "@/components/teams/TeamForm";

export default function TeamsPage() {
  const [teams, setTeams] = useState<Team[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);

  useEffect(() => {
    api.get<Team[]>("/api/teams")
      .then(setTeams)
      .finally(() => setLoading(false));
  }, []);

  const handleCreated = (team: Team) => {
    setTeams((prev) => [...prev, team]);
    setShowCreate(false);
  };

  const handleUpdated = (updated: Team) =>
    setTeams((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));

  const handleDeleted = (id: number) =>
    setTeams((prev) => prev.filter((t) => t.id !== id));

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-2xl font-bold text-gray-900">Teams</h1>
        <Button onClick={() => setShowCreate(true)}>New team</Button>
      </div>

      {loading ? (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      ) : (
        <TeamList teams={teams} onUpdate={handleUpdated} onDelete={handleDeleted} />
      )}

      <Modal open={showCreate} onClose={() => setShowCreate(false)} title="Create team">
        <TeamForm
          onSaved={handleCreated}
          onCancel={() => setShowCreate(false)}
        />
      </Modal>
    </div>
  );
}
