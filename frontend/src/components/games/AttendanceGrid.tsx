"use client";

import { useEffect, useState } from "react";
import { api, ApiError } from "@/lib/api";
import type { AttendanceRecord } from "@/lib/types";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";

type Status = "yes" | "no" | "maybe";

const STATUS_OPTIONS: { value: Status; label: string; classes: string }[] = [
  { value: "yes", label: "In", classes: "bg-green-100 text-green-700 hover:bg-green-200" },
  { value: "maybe", label: "Maybe", classes: "bg-yellow-100 text-yellow-700 hover:bg-yellow-200" },
  { value: "no", label: "Out", classes: "bg-red-100 text-red-700 hover:bg-red-200" },
];

interface AttendanceGridProps {
  gameId: number;
}

export function AttendanceGrid({ gameId }: AttendanceGridProps) {
  const [records, setRecords] = useState<AttendanceRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState<number | null>(null);

  useEffect(() => {
    api
      .get<AttendanceRecord[]>(`/api/games/${gameId}/attendance`)
      .then(setRecords)
      .finally(() => setLoading(false));
  }, [gameId]);

  const handleStatusChange = async (playerId: number, status: Status) => {
    setSaving(playerId);
    try {
      await api.put(`/api/games/${gameId}/attendance`, [{ player_id: playerId, status }]);
      setRecords((prev) =>
        prev.map((r) => (r.player_id === playerId ? { ...r, status } : r))
      );
    } catch (err) {
      alert(err instanceof ApiError ? err.message : "Failed to update attendance.");
    } finally {
      setSaving(null);
    }
  };

  if (loading) return <div className="flex justify-center py-4"><LoadingSpinner /></div>;

  if (records.length === 0) {
    return <p className="py-4 text-center text-sm text-gray-400">No players on roster.</p>;
  }

  return (
    <table className="w-full text-sm">
      <thead>
        <tr className="text-left text-xs text-gray-500">
          <th className="pb-2 font-medium">Player</th>
          <th className="pb-2 font-medium">Status</th>
        </tr>
      </thead>
      <tbody className="divide-y divide-gray-100">
        {records.map((record) => (
          <tr key={record.player_id}>
            <td className="py-2 font-medium text-gray-900">{record.player_name}</td>
            <td className="py-2">
              <div className="flex items-center gap-1">
                {saving === record.player_id ? (
                  <LoadingSpinner size="sm" />
                ) : (
                  STATUS_OPTIONS.map((opt) => (
                    <button
                      key={opt.value}
                      onClick={() => handleStatusChange(record.player_id, opt.value)}
                      className={`rounded-full px-2.5 py-0.5 text-xs font-medium transition-colors ${
                        record.status === opt.value
                          ? opt.classes
                          : "bg-gray-100 text-gray-400 hover:bg-gray-200"
                      }`}
                    >
                      {opt.label}
                    </button>
                  ))
                )}
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
