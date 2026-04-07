export interface LeagueConfig {
  label: string;
  pillBg: string;
  pillActiveBorder: string;
  groupBg: string;
  groupText: string;
  groupBorder: string;
  dot: string;
  bar: string;
}

export const LEAGUES: Record<string, LeagueConfig> = {
  PL:  { label: 'Premier League', pillBg: 'bg-purple-700', pillActiveBorder: 'border-purple-600', groupBg: 'bg-purple-950', groupText: 'text-purple-300', groupBorder: 'border-purple-800', dot: 'bg-purple-400', bar: 'bg-purple-500' },
  PD:  { label: 'La Liga',        pillBg: 'bg-orange-700', pillActiveBorder: 'border-orange-600', groupBg: 'bg-orange-950', groupText: 'text-orange-300', groupBorder: 'border-orange-800', dot: 'bg-orange-400', bar: 'bg-orange-500' },
  SA:  { label: 'Serie A',        pillBg: 'bg-blue-700',   pillActiveBorder: 'border-blue-600',   groupBg: 'bg-blue-950',   groupText: 'text-blue-300',   groupBorder: 'border-blue-800',   dot: 'bg-blue-400',   bar: 'bg-blue-500'   },
  BL1: { label: 'Bundesliga',     pillBg: 'bg-red-700',    pillActiveBorder: 'border-red-600',    groupBg: 'bg-red-950',    groupText: 'text-red-300',    groupBorder: 'border-red-800',    dot: 'bg-red-400',    bar: 'bg-red-500'    },
  FL1: { label: 'Ligue 1',        pillBg: 'bg-teal-700',   pillActiveBorder: 'border-teal-600',   groupBg: 'bg-teal-950',   groupText: 'text-teal-300',   groupBorder: 'border-teal-800',   dot: 'bg-teal-400',   bar: 'bg-teal-500'   },
};

export const LEAGUE_ORDER = ['PL', 'PD', 'SA', 'BL1', 'FL1'];
