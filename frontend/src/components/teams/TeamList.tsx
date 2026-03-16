"use client";

import { useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { Team } from "@/lib/types";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { TeamForm } from "./TeamForm";

interface TeamListProps {
  teams: Team[];
  onUpdate: (team: Team) => void;
  onDelete: (id: number) => void;
}

export function TeamList({ teams, onUpdate, onDelete }: TeamListProps) {
  const [editTarget, setEditTarget] = useState<Team | null>(null);
  const [deletingId, setDeletingId] = useState<number | null>(null);

  const handleDelete = async (team: Team) => {
    if (!confirm(`Delete "${team.name}"? This cannot be undone.`)) return;
    setDeletingId(team.id);
    try {
      await api.delete(`/api/teams/${team.id}`);
      onDelete(team.id);
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Failed to delete team.");
    } finally {
      setDeletingId(null);
    }
  };

  if (teams.length === 0) {
    return <p className="py-8 text-center text-sm text-gray-400">No teams yet. Create one to get started.</p>;
  }

  return (
    <>
      <ul className="divide-y divide-gray-200 rounded-lg border border-gray-200 bg-white">
        {teams.map((team) => (
          <li key={team.id} className="flex items-center justify-between px-4 py-3">
            <div>
              <p className="font-medium text-gray-900">{team.name}</p>
              <p className="text-xs text-gray-400">
                Created {new Date(team.created_at).toLocaleDateString()}
              </p>
            </div>
            <div className="flex items-center gap-2">
              <Button variant="secondary" onClick={() => setEditTarget(team)}>
                Edit
              </Button>
              <Button
                variant="danger"
                isLoading={deletingId === team.id}
                onClick={() => handleDelete(team)}
              >
                Delete
              </Button>
            </div>
          </li>
        ))}
      </ul>

      <Modal
        open={!!editTarget}
        onClose={() => setEditTarget(null)}
        title="Edit team"
      >
        {editTarget && (
          <TeamForm
            team={editTarget}
            onSaved={(updated) => {
              onUpdate(updated);
              setEditTarget(null);
            }}
            onCancel={() => setEditTarget(null)}
          />
        )}
      </Modal>
    </>
  );
}
