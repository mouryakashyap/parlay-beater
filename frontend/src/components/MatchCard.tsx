import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { fetchPredictionsForMatch } from "../api/client";
import type { Match } from "../types";
import PredictionBars from "./PredictionBars";

interface Props {
  match: Match;
  defaultExpanded?: boolean;
}

export default function MatchCard({ match, defaultExpanded = false }: Props) {
  const [expanded, setExpanded] = useState(defaultExpanded);

  const { data: predictions, isLoading } = useQuery({
    queryKey: ['predictions', 'match', match.id],
    queryFn: () => fetchPredictionsForMatch(match.id),
    enabled: expanded,
  });

  const kickoff = new Date(match.utc_date).toLocaleTimeString('en-GB', {
    hour: '2-digit',
    minute: '2-digit',
  });

  const isFinished = match.status === 'FINISHED';
  const isLive = match.status === 'LIVE';
  const prediction = predictions?.[0] ?? null;

  return (
    <div>
      {/* Collapsed row */}
      <button
        className="w-full px-4 py-3 flex items-center gap-3 hover:bg-gray-800/50 transition-colors text-left"
        onClick={() => setExpanded(e => !e)}
      >
        {/* Time */}
        <span className="text-xs text-gray-500 w-10 shrink-0 tabular-nums">{kickoff}</span>

        {/* Teams + score */}
        <div className="flex-1 flex items-center gap-2 min-w-0">
          <span className={`text-sm font-medium truncate ${isFinished && match.result === 'HOME' ? 'text-green-400' : 'text-gray-200'}`}>
            {match.home_team.name}
          </span>

          {isFinished ? (
            <span className="text-sm font-bold text-white px-2 shrink-0">
              {match.home_score} – {match.away_score}
            </span>
          ) : isLive ? (
            <span className="text-xs font-bold text-green-400 animate-pulse px-2 shrink-0">LIVE</span>
          ) : (
            <span className="text-xs text-gray-600 px-1 shrink-0">vs</span>
          )}

          <span className={`text-sm font-medium truncate ${isFinished && match.result === 'AWAY' ? 'text-green-400' : 'text-gray-200'}`}>
            {match.away_team.name}
          </span>
        </div>

        {/* Status + chevron */}
        <div className="flex items-center gap-2 shrink-0">
          {match.status === 'POSTPONED' && (
            <span className="text-xs text-yellow-500">Postponed</span>
          )}
          <span className="text-gray-600 text-xs">{expanded ? '▲' : '▼'}</span>
        </div>
      </button>

      {/* Expanded prediction panel */}
      {expanded && (
        <div className="px-4 pb-4 pt-2 bg-gray-950/60 border-t border-gray-800">
          {isLoading ? (
            <div className="space-y-2 animate-pulse">
              {[1, 2, 3].map(i => (
                <div key={i} className="flex items-center gap-3">
                  <div className="w-24 h-2 bg-gray-800 rounded" />
                  <div className="flex-1 h-1.5 bg-gray-800 rounded-full" />
                  <div className="w-9 h-2 bg-gray-800 rounded" />
                </div>
              ))}
            </div>
          ) : prediction ? (
            <PredictionBars prediction={prediction} match={match} />
          ) : (
            <p className="text-xs text-gray-600">No prediction available — model not yet trained.</p>
          )}
        </div>
      )}
    </div>
  );
}
