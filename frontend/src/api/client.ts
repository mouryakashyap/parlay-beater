/**
 * Axios client — single instance used across all API calls.
 * TanStack Query wraps these functions and handles caching/refetching.
 */

import axios from "axios";
import type { MatchListResponse, Prediction, Team } from "../types";

const api = axios.create({
  baseURL: "/api/v1",
  headers: { "Content-Type": "application/json" },
});

// ── Matches ────────────────────────────────────────────────────────────────

export const fetchUpcomingMatches = (league?: string, days = 7): Promise<MatchListResponse> =>
  api.get("/matches/upcoming", { params: { league, days } }).then((r) => r.data);

export const fetchFinishedMatches = (daysBack = 7): Promise<MatchListResponse> =>
  api.get("/matches/finished", { params: { days_back: daysBack } }).then((r) => r.data);

// ── Predictions ────────────────────────────────────────────────────────────

export const fetchPredictionsForMatch = (matchId: number): Promise<Prediction[]> =>
  api.get(`/predictions/match/${matchId}`).then((r) => r.data);

export const fetchRecentPredictions = (limit = 50): Promise<Prediction[]> =>
  api.get("/predictions/recent", { params: { limit } }).then((r) => r.data);

// ── Teams ──────────────────────────────────────────────────────────────────

export const fetchTeams = (league?: string): Promise<Team[]> =>
  api.get("/teams", { params: { league } }).then((r) => r.data);
