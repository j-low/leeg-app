// TypeScript interfaces matching backend Pydantic schemas

export interface User {
  id: number;
  email: string;
  phone: string | null;
  is_captain: boolean;
  is_active: boolean;
  created_at: string;
}

export interface Team {
  id: number;
  name: string;
  captain_id: number;
  created_at: string;
  updated_at: string;
}

export interface Player {
  id: number;
  name: string;
  phone: string;
  team_id: number;
  position_prefs: string[];
  sub_flag: boolean;
  skill_notes: string | null;
  captain_notes: string | null;
}

export interface Season {
  id: number;
  name: string;
  start_date: string;
  end_date: string;
  status: "open" | "closed";
  created_at: string;
}

export interface Game {
  id: number;
  date: string;
  time: string;
  location: string;
  season_id: number | null;
  standalone: boolean;
  notes: string | null;
}

export interface AttendanceRecord {
  player_id: number;
  player_name: string;
  status: "yes" | "no" | "maybe" | null;
}

export interface Lineup {
  id: number;
  game_id: number;
  proposed_lines: Record<string, unknown>;
  criteria: string | null;
  explanation: string | null;
  created_at: string;
}

// ── SSE Chat events ──────────────────────────────────────────────────────────

export type ChatEvent =
  | { type: "answer_token"; text: string }
  | { type: "tool_start"; name: string; input: Record<string, unknown> }
  | { type: "tool_result"; name: string; result: unknown }
  | { type: "done"; text_for_user: string; mutations: string[] }
  | { type: "error"; message: string }
  | { type: "ping" };

export interface ToolCall {
  name: string;
  done: boolean;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  text: string;
  isStreaming?: boolean;
  toolCalls?: ToolCall[];
  isError?: boolean;
}

// ── API helpers ───────────────────────────────────────────────────────────────

export interface ApiError {
  status: number;
  message: string;
}

export interface TokenResponse {
  access_token: string;
  token_type: string;
}

// ── Form payloads ─────────────────────────────────────────────────────────────

export interface TeamCreate {
  name: string;
}

export interface PlayerCreate {
  name: string;
  phone: string;
  team_id: number;
  position_prefs: string[];
  sub_flag: boolean;
  skill_notes?: string;
}

export interface AttendanceUpdate {
  player_id: number;
  status: "yes" | "no" | "maybe";
}
