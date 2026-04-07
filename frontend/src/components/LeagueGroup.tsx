import type { ReactNode } from "react";
import { LEAGUES } from "../lib/leagues";

interface Props {
  league: string;
  matchCount: number;
  children: ReactNode;
}

export default function LeagueGroup({ league, matchCount, children }: Props) {
  const cfg = LEAGUES[league];
  const label = cfg?.label ?? league;
  const headerBg = cfg?.groupBg ?? 'bg-gray-800';
  const headerText = cfg?.groupText ?? 'text-gray-300';
  const borderColor = cfg?.groupBorder ?? 'border-gray-700';

  return (
    <div className="mb-5">
      <div className={`flex items-center justify-between px-4 py-2.5 rounded-t-lg border ${headerBg} ${borderColor}`}>
        <span className={`text-sm font-bold tracking-wide ${headerText}`}>{label}</span>
        <span className="text-xs text-gray-600">{matchCount} {matchCount === 1 ? 'match' : 'matches'}</span>
      </div>
      <div className={`border border-t-0 ${borderColor} rounded-b-lg overflow-hidden divide-y divide-gray-800`}>
        {children}
      </div>
    </div>
  );
}
