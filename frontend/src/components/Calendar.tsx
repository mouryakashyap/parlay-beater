import { useState } from "react";
import { LEAGUES } from "../lib/leagues";
import type { Match } from "../types";

interface Props {
  matches: Match[];
  selectedDate: string;    // "YYYY-MM-DD"
  onSelectDate: (date: string) => void;
}

const DOW_LABELS = ['Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa', 'Su'];

export default function Calendar({ matches, selectedDate, onSelectDate }: Props) {
  const today = new Date();
  const [viewYear, setViewYear] = useState(today.getFullYear());
  const [viewMonth, setViewMonth] = useState(today.getMonth());

  // Build date → league set map
  const matchDateMap = new Map<string, Set<string>>();
  for (const m of matches) {
    const d = new Date(m.utc_date).toLocaleDateString('en-CA');
    if (!matchDateMap.has(d)) matchDateMap.set(d, new Set());
    matchDateMap.get(d)!.add(m.league);
  }

  const firstDow = new Date(viewYear, viewMonth, 1).getDay();
  const daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();
  const offset = (firstDow + 6) % 7; // shift so Mon = 0

  const cells: (number | null)[] = [
    ...Array(offset).fill(null),
    ...Array.from({ length: daysInMonth }, (_, i) => i + 1),
  ];
  while (cells.length % 7 !== 0) cells.push(null);

  const todayStr = today.toLocaleDateString('en-CA');
  const monthLabel = new Date(viewYear, viewMonth).toLocaleDateString('en-US', {
    month: 'long', year: 'numeric',
  });

  function prevMonth() {
    if (viewMonth === 0) { setViewYear(y => y - 1); setViewMonth(11); }
    else setViewMonth(m => m - 1);
  }
  function nextMonth() {
    if (viewMonth === 11) { setViewYear(y => y + 1); setViewMonth(0); }
    else setViewMonth(m => m + 1);
  }

  return (
    <div className="bg-gray-900 border border-gray-800 rounded-xl p-4 w-64 shrink-0 self-start">
      {/* Header */}
      <div className="flex items-center justify-between mb-3">
        <button
          onClick={prevMonth}
          className="w-7 h-7 flex items-center justify-center rounded hover:bg-gray-800 text-gray-400 hover:text-white transition-colors text-sm"
        >
          ‹
        </button>
        <span className="text-sm font-semibold text-gray-100">{monthLabel}</span>
        <button
          onClick={nextMonth}
          className="w-7 h-7 flex items-center justify-center rounded hover:bg-gray-800 text-gray-400 hover:text-white transition-colors text-sm"
        >
          ›
        </button>
      </div>

      {/* Day-of-week labels */}
      <div className="grid grid-cols-7 mb-1">
        {DOW_LABELS.map(d => (
          <div key={d} className="text-center text-xs text-gray-600 py-1">{d}</div>
        ))}
      </div>

      {/* Day grid */}
      <div className="grid grid-cols-7 gap-y-0.5">
        {cells.map((day, i) => {
          if (day === null) return <div key={i} />;
          const dateStr = `${viewYear}-${String(viewMonth + 1).padStart(2, '0')}-${String(day).padStart(2, '0')}`;
          const leagues = matchDateMap.get(dateStr);
          const isSelected = dateStr === selectedDate;
          const isToday = dateStr === todayStr;
          const hasMatches = leagues && leagues.size > 0;

          return (
            <button
              key={i}
              onClick={() => onSelectDate(dateStr)}
              className={`
                relative flex flex-col items-center justify-center py-1 rounded-md text-xs font-medium transition-all
                ${isSelected
                  ? 'bg-green-600 text-white'
                  : isToday
                    ? 'ring-1 ring-green-600 text-green-400 hover:bg-gray-800'
                    : 'text-gray-300 hover:bg-gray-800'}
                ${hasMatches && !isSelected ? 'font-semibold' : ''}
              `}
            >
              {day}
              {hasMatches && (
                <div className="flex gap-0.5 mt-0.5">
                  {[...leagues!].slice(0, 3).map(l => (
                    <span
                      key={l}
                      className={`block w-1 h-1 rounded-full ${LEAGUES[l]?.dot ?? 'bg-gray-500'} ${isSelected ? 'opacity-80' : ''}`}
                    />
                  ))}
                </div>
              )}
            </button>
          );
        })}
      </div>

      {/* Legend */}
      <div className="mt-3 pt-3 border-t border-gray-800 grid grid-cols-2 gap-x-2 gap-y-1">
        {Object.entries(LEAGUES).map(([code, cfg]) => (
          <div key={code} className="flex items-center gap-1.5">
            <span className={`w-1.5 h-1.5 rounded-full ${cfg.dot} shrink-0`} />
            <span className="text-xs text-gray-500 truncate">{cfg.label}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
