import { useQuery } from "@tanstack/react-query";
import { fetchUpcomingMatches, fetchFinishedMatches } from "../api/client";
import type { Match } from "../types";

export function useCalendarMatches() {
  const { data: upcoming, isLoading: loadingUp } = useQuery({
    queryKey: ['matches', 'upcoming', 30],
    queryFn: () => fetchUpcomingMatches(undefined, 30),
  });

  const { data: finished, isLoading: loadingFin } = useQuery({
    queryKey: ['matches', 'finished', 90],
    queryFn: () => fetchFinishedMatches(90),
  });

  const all: Match[] = [
    ...(upcoming?.items ?? []),
    ...(finished?.items ?? []),
  ];

  // Group by local date "YYYY-MM-DD" using en-CA locale (gives ISO format)
  const byDate = new Map<string, Match[]>();
  for (const m of all) {
    const d = new Date(m.utc_date).toLocaleDateString('en-CA');
    if (!byDate.has(d)) byDate.set(d, []);
    byDate.get(d)!.push(m);
  }

  return { all, byDate, isLoading: loadingUp || loadingFin };
}
