"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useAuth } from "@/contexts/AuthContext";
import { api } from "@/lib/api";
import type { Team, Game } from "@/lib/types";
import { LoadingSpinner } from "@/components/ui/LoadingSpinner";

export default function DashboardPage() {
  const { user } = useAuth();
  const [teams, setTeams] = useState<Team[]>([]);
  const [games, setGames] = useState<Game[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      api.get<Team[]>("/api/teams"),
      api.get<Game[]>("/api/games"),
    ])
      .then(([t, g]) => {
        setTeams(t);
        setGames(g);
      })
      .finally(() => setLoading(false));
  }, []);

  const nextGame = games
    .filter((g) => new Date(`${g.date}T${g.time}`) > new Date())
    .sort((a, b) => new Date(`${a.date}T${a.time}`).getTime() - new Date(`${b.date}T${b.time}`).getTime())[0];

  return (
    <div className="p-8">
      <h1 className="mb-1 text-2xl font-bold text-gray-900">
        Welcome back{user?.email ? `, ${user.email.split("@")[0]}` : ""}
      </h1>
      <p className="mb-8 text-sm text-gray-500">Here&apos;s what&apos;s happening with your team.</p>

      {loading ? (
        <div className="flex justify-center py-12">
          <LoadingSpinner />
        </div>
      ) : (
        <div className="grid gap-6 sm:grid-cols-2 lg:grid-cols-3">
          <StatCard
            title="Teams"
            value={teams.length}
            description="managed"
            href="/teams"
            linkLabel="Manage teams"
          />
          <StatCard
            title="Total games"
            value={games.length}
            description="scheduled"
            href="/games"
            linkLabel="View games"
          />
          <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
            <p className="text-sm font-medium text-gray-500">Next game</p>
            {nextGame ? (
              <>
                <p className="mt-1 text-lg font-semibold text-gray-900">{nextGame.date}</p>
                <p className="text-sm text-gray-600">
                  {nextGame.time} · {nextGame.location}
                </p>
              </>
            ) : (
              <p className="mt-1 text-sm text-gray-400">No upcoming games</p>
            )}
            <Link href="/games" className="mt-3 block text-xs text-blue-600 hover:underline">
              View games →
            </Link>
          </div>
        </div>
      )}

      <div className="mt-10">
        <h2 className="mb-4 text-base font-semibold text-gray-900">Quick actions</h2>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <QuickLink href="/chat" label="Ask the AI" description="Natural language team management" />
          <QuickLink href="/roster" label="Manage roster" description="Add or edit players" />
          <QuickLink href="/games" label="Record attendance" description="Track who's playing" />
          <QuickLink href="/lineups" label="Suggest lineup" description="AI-generated ice time" />
        </div>
      </div>
    </div>
  );
}

function StatCard({
  title,
  value,
  description,
  href,
  linkLabel,
}: {
  title: string;
  value: number;
  description: string;
  href: string;
  linkLabel: string;
}) {
  return (
    <div className="rounded-xl border border-gray-200 bg-white p-5 shadow-sm">
      <p className="text-sm font-medium text-gray-500">{title}</p>
      <p className="mt-1 text-3xl font-bold text-gray-900">{value}</p>
      <p className="text-sm text-gray-400">{description}</p>
      <Link href={href} className="mt-3 block text-xs text-blue-600 hover:underline">
        {linkLabel} →
      </Link>
    </div>
  );
}

function QuickLink({ href, label, description }: { href: string; label: string; description: string }) {
  return (
    <Link
      href={href}
      className="rounded-lg border border-gray-200 bg-white p-4 shadow-sm transition-shadow hover:shadow-md"
    >
      <p className="text-sm font-semibold text-gray-900">{label}</p>
      <p className="mt-0.5 text-xs text-gray-500">{description}</p>
    </Link>
  );
}
