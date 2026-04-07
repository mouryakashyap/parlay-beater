import { useSearchParams } from "react-router-dom";
import { useQueries } from "@tanstack/react-query";
import Calendar from "../components/Calendar";
import LeaguePills from "../components/LeaguePills";
import LeagueGroup from "../components/LeagueGroup";
import MatchCard from "../components/MatchCard";
import { useLeagueFilter } from "../hooks/useLeagueFilter";
import { useCalendarMatches } from "../hooks/useCalendarMatches";
import { fetchPredictionsForMatch } from "../api/client";
import { LEAGUE_ORDER } from "../lib/leagues";

const todayStr = new Date().toLocaleDateString('en-CA');

export default function Dashboard() {
  const [params, setParams] = useSearchParams();
  const selectedDate = params.get('date') ?? todayStr;

  function selectDate(date: string) {
    setParams(p => { p.set('date', date); return p; });
  }

  const { all, byDate, isLoading } = useCalendarMatches();
  const { activeLeagues, toggle, filterMatches } = useLeagueFilter();

  const rawDayMatches = byDate.get(selectedDate) ?? [];

  // Prefetch predictions for every match on the selected day in parallel.
  // MatchCard uses the same queryKey, so it reads from cache instantly on expand.
  useQueries({
    queries: rawDayMatches.map(m => ({
      queryKey: ['predictions', 'match', m.id] as const,
      queryFn: () => fetchPredictionsForMatch(m.id),
    })),
  });
  const dayMatches = filterMatches(rawDayMatches);

  // Group by league in a fixed order
  const grouped = LEAGUE_ORDER.reduce<Record<string, typeof dayMatches>>((acc, l) => {
    const ms = dayMatches.filter(m => m.league === l);
    if (ms.length > 0) acc[l] = ms;
    return acc;
  }, {});
  // Also capture any unknown leagues not in LEAGUE_ORDER
  const knownLeagues = new Set(LEAGUE_ORDER);
  dayMatches
    .filter(m => !knownLeagues.has(m.league))
    .forEach(m => {
      if (!grouped[m.league]) grouped[m.league] = [];
      grouped[m.league].push(m);
    });

  const dateLabel = new Date(selectedDate + 'T00:00:00').toLocaleDateString('en-US', {
    weekday: 'long', month: 'long', day: 'numeric', year: 'numeric',
  });

  return (
    <div className="space-y-5">
      <LeaguePills activeLeagues={activeLeagues} onToggle={toggle} />

      <div className="flex gap-6 items-start">
        {/* Left: calendar */}
        <div>
          <Calendar matches={all} selectedDate={selectedDate} onSelectDate={selectDate} />
        </div>

        {/* Right: matches for the day */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-300">{dateLabel}</h2>
            {rawDayMatches.length > 0 && (
              <span className="text-xs text-gray-600">{rawDayMatches.length} match{rawDayMatches.length !== 1 ? 'es' : ''}</span>
            )}
          </div>

          {isLoading ? (
            <div className="space-y-4">
              {[1, 2].map(i => (
                <div key={i} className="bg-gray-900 border border-gray-800 rounded-lg h-16 animate-pulse" />
              ))}
            </div>
          ) : Object.keys(grouped).length === 0 ? (
            <div className="bg-gray-900 border border-gray-800 rounded-lg p-10 text-center">
              <p className="text-gray-500 text-sm">No matches on this day.</p>
              {all.length === 0 && (
                <p className="text-gray-700 text-xs mt-1">Run data ingestion to populate match data.</p>
              )}
            </div>
          ) : (
            Object.entries(grouped).map(([league, matches]) => (
              <LeagueGroup key={league} league={league} matchCount={matches.length}>
                {matches.map(m => <MatchCard key={m.id} match={m} />)}
              </LeagueGroup>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
