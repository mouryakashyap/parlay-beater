import { useQuery } from "@tanstack/react-query";
import { fetchFinishedMatches, fetchPredictionsForMatch } from "../api/client";
import LeaguePills from "../components/LeaguePills";
import LeagueGroup from "../components/LeagueGroup";
import { useLeagueFilter } from "../hooks/useLeagueFilter";
import { LEAGUE_ORDER } from "../lib/leagues";
import type { Match, Prediction } from "../types";

function AccuracyBadge({ correct, label }: { correct: boolean | null; label: string }) {
  if (correct === null) return (
    <span className="text-xs text-gray-700 border border-gray-800 px-2 py-0.5 rounded">{label}: —</span>
  );
  return (
    <span className={`text-xs px-2 py-0.5 rounded border font-medium ${
      correct
        ? 'bg-green-900/50 text-green-400 border-green-800'
        : 'bg-red-900/50 text-red-400 border-red-800'
    }`}>
      {correct ? '✓' : '✗'} {label}
    </span>
  );
}

function HistoryCard({ match }: { match: Match }) {
  const { data: predictions } = useQuery({
    queryKey: ['predictions', 'match', match.id],
    queryFn: () => fetchPredictionsForMatch(match.id),
  });

  const prediction: Prediction | null = predictions?.[0] ?? null;
  const date = new Date(match.utc_date).toLocaleDateString('en-US', {
    weekday: 'short', month: 'short', day: 'numeric',
  });

  const resultLabel = match.result === 'HOME'
    ? match.home_team.short_name ?? match.home_team.name
    : match.result === 'AWAY'
      ? match.away_team.short_name ?? match.away_team.name
      : 'Draw';

  return (
    <div className="px-4 py-3 flex items-center gap-4">
      {/* Date */}
      <span className="text-xs text-gray-600 w-20 shrink-0">{date}</span>

      {/* Teams + score */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-sm">
          <span className={`font-medium truncate ${match.result === 'HOME' ? 'text-green-400' : 'text-gray-300'}`}>
            {match.home_team.name}
          </span>
          <span className="font-bold text-white shrink-0">
            {match.home_score} – {match.away_score}
          </span>
          <span className={`font-medium truncate ${match.result === 'AWAY' ? 'text-green-400' : 'text-gray-300'}`}>
            {match.away_team.name}
          </span>
        </div>
        {match.result && (
          <p className="text-xs text-gray-600 mt-0.5">Result: {resultLabel} win{match.result === 'DRAW' ? '' : ''}</p>
        )}
      </div>

      {/* Accuracy badges */}
      {prediction ? (
        <div className="flex gap-1.5 shrink-0 flex-wrap justify-end">
          <AccuracyBadge correct={prediction.result_correct} label="Result" />
          <AccuracyBadge correct={prediction.btts_correct} label="BTTS" />
          <AccuracyBadge correct={prediction.over_25_correct} label="O2.5" />
        </div>
      ) : (
        <span className="text-xs text-gray-700 shrink-0">No prediction</span>
      )}
    </div>
  );
}

function LeagueAccuracySummary({ matches, leaguePredictions }: {
  matches: Match[];
  leaguePredictions: Map<number, Prediction | null>;
}) {
  const withPredictions = matches.filter(m => leaguePredictions.get(m.id));
  const correct = withPredictions.filter(m => leaguePredictions.get(m.id)?.result_correct === true);

  if (withPredictions.length === 0) return null;

  const pct = Math.round((correct.length / withPredictions.length) * 100);
  return (
    <div className="px-4 py-2 border-t border-gray-800 bg-gray-900/50 flex items-center justify-between">
      <span className="text-xs text-gray-600">Result accuracy</span>
      <span className={`text-xs font-bold ${pct >= 60 ? 'text-green-400' : pct >= 40 ? 'text-yellow-400' : 'text-red-400'}`}>
        {correct.length}/{withPredictions.length} ({pct}%)
      </span>
    </div>
  );
}

export default function History() {
  const { activeLeagues, toggle, filterMatches } = useLeagueFilter();

  const { data, isLoading } = useQuery({
    queryKey: ['matches', 'finished', 30],
    queryFn: () => fetchFinishedMatches(30),
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
        <h1 className="text-lg font-bold text-gray-100">Results History</h1>
        <span className="text-xs text-gray-600">Last 30 days</span>
      </div>

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map(i => <div key={i} className="h-16 bg-gray-900 border border-gray-800 rounded-lg animate-pulse" />)}
        </div>
      ) : Object.keys(grouped).length === 0 ? (
        <div className="bg-gray-900 border border-gray-800 rounded-lg p-10 text-center">
          <p className="text-gray-500 text-sm">No finished matches in the last 30 days.</p>
        </div>
      ) : (
        Object.entries(grouped).map(([league, leagueMatches]) => (
          <LeagueGroup key={league} league={league} matchCount={leagueMatches.length}>
            <div className="divide-y divide-gray-800">
              {leagueMatches.map(m => <HistoryCard key={m.id} match={m} />)}
            </div>
            <LeagueAccuracySummary matches={leagueMatches} leaguePredictions={new Map()} />
          </LeagueGroup>
        ))
      )}
    </div>
  );
}
