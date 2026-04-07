import { useQuery, useQueries } from "@tanstack/react-query";
import { fetchUpcomingMatches, fetchPredictionsForMatch } from "../api/client";
import LeaguePills from "../components/LeaguePills";
import LeagueGroup from "../components/LeagueGroup";
import MatchCard from "../components/MatchCard";
import { useLeagueFilter } from "../hooks/useLeagueFilter";
import { LEAGUE_ORDER } from "../lib/leagues";
import type { Match } from "../types";

export default function Dashboard() {
  const { activeLeagues, toggle, filterMatches } = useLeagueFilter();

  const { data, isLoading } = useQuery({
    queryKey: ["matches", "upcoming", 7],
    queryFn: () => fetchUpcomingMatches(undefined, 7),
  });

  const allMatches: Match[] = data?.items ?? [];
  const matches = filterMatches(allMatches);

  // Prefetch predictions for all upcoming matches in parallel
  useQueries({
    queries: allMatches.map((m) => ({
      queryKey: ["predictions", "match", m.id] as const,
      queryFn: () => fetchPredictionsForMatch(m.id),
    })),
  });

  // Group by league in fixed order
  const grouped = LEAGUE_ORDER.reduce<Record<string, Match[]>>((acc, l) => {
    const ms = matches.filter((m) => m.league === l);
    if (ms.length > 0) acc[l] = ms;
    return acc;
  }, {});
  // Catch any leagues outside LEAGUE_ORDER
  const known = new Set(LEAGUE_ORDER);
  matches
    .filter((m) => !known.has(m.league))
    .forEach((m) => {
      if (!grouped[m.league]) grouped[m.league] = [];
      grouped[m.league].push(m);
    });

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-gray-100">Upcoming Matches</h1>
        <span className="text-xs text-gray-600">Next 7 days</span>
      </div>

      <LeaguePills activeLeagues={activeLeagues} onToggle={toggle} />

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map((i) => (
            <div key={i} className="h-16 bg-gray-900 border border-gray-800 rounded-lg animate-pulse" />
          ))}
        </div>
      ) : Object.keys(grouped).length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-10 text-center">
          <p className="text-gray-500 text-sm">No upcoming matches.</p>
          {allMatches.length === 0 && (
            <p className="text-gray-700 text-xs mt-1">Run data ingestion to populate match data.</p>
          )}
        </div>
      ) : (
        Object.entries(grouped).map(([league, leagueMatches]) => (
          <LeagueGroup key={league} league={league} matchCount={leagueMatches.length}>
            {leagueMatches.map((m) => (
              <MatchCard key={m.id} match={m} />
            ))}
          </LeagueGroup>
        ))
      )}
    </div>
  );
}
