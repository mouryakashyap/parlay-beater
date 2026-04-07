import type { Prediction, Match } from "../types";
import ConfidenceBadge from "./ConfidenceBadge";

interface BarProps {
  label: string;
  value: number | null;
  colorClass: string;
}

function Bar({ label, value, colorClass }: BarProps) {
  const pct = value !== null ? Math.round(value * 100) : 0;
  return (
    <div className="flex items-center gap-3">
      <span className="text-xs text-gray-400 w-24 truncate shrink-0">{label}</span>
      <div className="flex-1 bg-gray-800 rounded-full h-1.5 overflow-hidden">
        <div
          className={`h-1.5 rounded-full ${colorClass} transition-all duration-700`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-300 w-9 text-right tabular-nums">{pct}%</span>
    </div>
  );
}

interface Props {
  prediction: Prediction;
  match: Match;
}

export default function PredictionBars({ prediction, match }: Props) {
  return (
    <div className="space-y-2">
      <Bar
        label={match.home_team.short_name ?? match.home_team.name}
        value={prediction.result_home}
        colorClass="bg-green-500"
      />
      <Bar label="Draw" value={prediction.result_draw} colorClass="bg-gray-500" />
      <Bar
        label={match.away_team.short_name ?? match.away_team.name}
        value={prediction.result_away}
        colorClass="bg-blue-500"
      />

      <div className="flex items-center gap-4 pt-2 border-t border-gray-800 mt-2">
        <span className="text-xs text-gray-500">
          BTTS{' '}
          <span className="text-gray-200 font-medium tabular-nums">
            {prediction.btts !== null ? `${Math.round(prediction.btts * 100)}%` : '—'}
          </span>
        </span>
        <span className="text-xs text-gray-500">
          Over 2.5{' '}
          <span className="text-gray-200 font-medium tabular-nums">
            {prediction.over_25 !== null ? `${Math.round(prediction.over_25 * 100)}%` : '—'}
          </span>
        </span>
        <span className="ml-auto">
          <ConfidenceBadge confidence={prediction.confidence} />
        </span>
      </div>
    </div>
  );
}
