import { useQuery } from "@tanstack/react-query";
import { fetchUpcomingMatches, fetchPredictionsForMatch } from "../api/client";
import LeaguePills from "../components/LeaguePills";
import LeagueGroup from "../components/LeagueGroup";
import PredictionBars from "../components/PredictionBars";
import ConfidenceBadge from "../components/ConfidenceBadge";
import { useLeagueFilter } from "../hooks/useLeagueFilter";
import { LEAGUE_ORDER } from "../lib/leagues";
import type { Match } from "../types";

function PredictionCard({ match }: { match: Match }) {
  const { data: predictions, isLoading } = useQuery({
    queryKey: ['predictions', 'match', match.id],
    queryFn: () => fetchPredictionsForMatch(match.id),
  });

  const prediction = predictions?.[0] ?? null;
  const kickoff = new Date(match.utc_date).toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
  });
  const time = new Date(match.utc_date).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' });

  return (
    <div className="px-4 py-4">
      <div className="flex items-center justify-between mb-3">
        <div>
          <span className="text-sm font-semibold text-gray-200">
            {match.home_team.name} <span className="text-gray-600 font-normal">vs</span> {match.away_team.name}
          </span>
          <div className="text-xs text-gray-600 mt-0.5">{kickoff} · {time}</div>
        </div>
        {prediction && <ConfidenceBadge confidence={prediction.confidence} />}
      </div>

      {isLoading ? (
        <div className="space-y-2 animate-pulse">
          {[1, 2, 3].map(i => (
            <div key={i} className="flex gap-3 items-center">
              <div className="w-24 h-2 bg-gray-800 rounded" />
              <div className="flex-1 h-1.5 bg-gray-800 rounded-full" />
            </div>
          ))}
        </div>
      ) : prediction ? (
        <PredictionBars prediction={prediction} match={match} />
      ) : (
        <p className="text-xs text-gray-600">No prediction — model not yet trained.</p>
      )}
    </div>
  );
}

export default function Predictions() {
  const { activeLeagues, toggle, filterMatches } = useLeagueFilter();

  const { data, isLoading } = useQuery({
    queryKey: ['matches', 'upcoming', 7],
    queryFn: () => fetchUpcomingMatches(undefined, 7),
  });

  const matches = filterMatches(data?.items ?? []);

  const grouped = LEAGUE_ORDER.reduce<Record<string, Match[]>>((acc, l) => {
    const ms = matches.filter(m => m.league === l);
    if (ms.length > 0) acc[l] = ms;
    return acc;
  }, {});

  return (
    <div className="space-y-5">
      <LeaguePills activeLeagues={activeLeagues} onToggle={toggle} />

      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold text-gray-100">Upcoming Predictions</h1>
        <span className="text-xs text-gray-600">Next 7 days</span>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map(i => <div key={i} className="h-24 bg-gray-900 border border-gray-800 rounded-lg animate-pulse" />)}
        </div>
      ) : Object.keys(grouped).length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-10 text-center">
          <p className="text-gray-500 text-sm">No upcoming matches.</p>
          {(data?.total ?? 0) === 0 && (
            <p className="text-gray-700 text-xs mt-1">Run data ingestion to populate match data.</p>
          )}
        </div>
      ) : (
        Object.entries(grouped).map(([league, leagueMatches]) => (
          <LeagueGroup key={league} league={league} matchCount={leagueMatches.length}>
            <div className="divide-y divide-gray-800">
              {leagueMatches.map(m => <PredictionCard key={m.id} match={m} />)}
            </div>
          </LeagueGroup>
        ))
      )}
    </div>
  );
}
