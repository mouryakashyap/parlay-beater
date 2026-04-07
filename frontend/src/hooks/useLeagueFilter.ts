import { useState } from "react";

export function useLeagueFilter() {
  const [activeLeagues, setActiveLeagues] = useState<string[]>([]);

  function toggle(league: string) {
    if (league === 'ALL') {
      setActiveLeagues([]);
      return;
    }
    setActiveLeagues(prev =>
      prev.includes(league) ? prev.filter(l => l !== league) : [...prev, league]
    );
  }

  function filterMatches<T extends { league: string }>(items: T[]): T[] {
    if (activeLeagues.length === 0) return items;
    return items.filter(m => activeLeagues.includes(m.league));
  }

  return { activeLeagues, toggle, filterMatches };
}
