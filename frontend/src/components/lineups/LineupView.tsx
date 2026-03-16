import type { Lineup } from "@/lib/types";

type LineGroup = { line: number | string; players: string[] };
type GroupedLines = { forwards: LineGroup[]; defense: LineGroup[]; goalies: string[] };

function parseLines(proposed: Record<string, unknown>): GroupedLines {
  const result: GroupedLines = { forwards: [], defense: [], goalies: [] };

  // Support both {forwards: [...], defense: [...], goalies: [...]}
  // and {lines: [{line: 1, players: [...]}]} formats
  const raw = proposed as Record<string, unknown>;

  const toNames = (arr: unknown): string[] => {
    if (!Array.isArray(arr)) return [];
    return arr.map((p) =>
      typeof p === "string" ? p : (p as Record<string, string>)?.name ?? JSON.stringify(p)
    );
  };

  if (raw.forwards || raw.defense || raw.goalies) {
    const fwd = raw.forwards as unknown[];
    const def = raw.defense as unknown[];
    const gtl = raw.goalies as unknown[];

    if (Array.isArray(fwd) && fwd.length > 0) {
      if (typeof fwd[0] === "object" && (fwd[0] as Record<string,unknown>).players) {
        result.forwards = (fwd as {line: unknown; players: unknown[]}[]).map((g) => ({
          line: g.line as number,
          players: toNames(g.players),
        }));
      } else {
        result.forwards = [{ line: 1, players: toNames(fwd) }];
      }
    }

    if (Array.isArray(def) && def.length > 0) {
      if (typeof def[0] === "object" && (def[0] as Record<string,unknown>).players) {
        result.defense = (def as {line: unknown; players: unknown[]}[]).map((g) => ({
          line: g.line as number,
          players: toNames(g.players),
        }));
      } else {
        result.defense = [{ line: 1, players: toNames(def) }];
      }
    }

    result.goalies = toNames(gtl);
  }

  return result;
}

interface LineupViewProps {
  lineup: Lineup;
}

export function LineupView({ lineup }: LineupViewProps) {
  const lines = parseLines(lineup.proposed_lines);

  return (
    <div className="space-y-4">
      {lineup.explanation && (
        <p className="text-sm text-gray-600 italic">{lineup.explanation}</p>
      )}

      {lines.forwards.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Forwards</h3>
          <div className="space-y-1.5">
            {lines.forwards.map((group) => (
              <div key={String(group.line)} className="flex items-center gap-2">
                <span className="w-14 shrink-0 text-xs text-gray-400">Line {group.line}</span>
                <div className="flex flex-wrap gap-1">
                  {group.players.map((name) => (
                    <PlayerPill key={name} name={name} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {lines.defense.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Defense</h3>
          <div className="space-y-1.5">
            {lines.defense.map((group) => (
              <div key={String(group.line)} className="flex items-center gap-2">
                <span className="w-14 shrink-0 text-xs text-gray-400">Pair {group.line}</span>
                <div className="flex flex-wrap gap-1">
                  {group.players.map((name) => (
                    <PlayerPill key={name} name={name} />
                  ))}
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {lines.goalies.length > 0 && (
        <section>
          <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-gray-400">Goalies</h3>
          <div className="flex flex-wrap gap-1">
            {lines.goalies.map((name) => (
              <PlayerPill key={name} name={name} />
            ))}
          </div>
        </section>
      )}

      {lines.forwards.length === 0 && lines.defense.length === 0 && lines.goalies.length === 0 && (
        <pre className="rounded-md bg-gray-50 p-3 text-xs text-gray-500 overflow-auto">
          {JSON.stringify(lineup.proposed_lines, null, 2)}
        </pre>
      )}
    </div>
  );
}

function PlayerPill({ name }: { name: string }) {
  return (
    <span className="rounded-full bg-blue-50 px-2.5 py-0.5 text-xs font-medium text-blue-700">
      {name}
    </span>
  );
}
