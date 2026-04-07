import { LEAGUES, LEAGUE_ORDER } from "../lib/leagues";

interface Props {
  activeLeagues: string[];
  onToggle: (league: string) => void;
}

export default function LeaguePills({ activeLeagues, onToggle }: Props) {
  const allActive = activeLeagues.length === 0;

  return (
    <div className="flex gap-2 flex-wrap items-center">
      <button
        onClick={() => onToggle('ALL')}
        className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
          allActive
            ? 'bg-green-700 border-green-600 text-white'
            : 'border-gray-700 text-gray-500 hover:border-gray-500 hover:text-gray-300'
        }`}
      >
        All
      </button>
      {LEAGUE_ORDER.map(code => {
        const cfg = LEAGUES[code];
        const isActive = activeLeagues.includes(code);
        return (
          <button
            key={code}
            onClick={() => onToggle(code)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-all ${
              isActive
                ? `${cfg.pillBg} ${cfg.pillActiveBorder} text-white`
                : 'border-gray-700 text-gray-500 hover:border-gray-500 hover:text-gray-300'
            }`}
          >
            {cfg.label}
          </button>
        );
      })}
    </div>
  );
}
