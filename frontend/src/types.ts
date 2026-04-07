export interface Team {
  id: number;
  name: string;
  short_name: string | null;
  league: string;
  country: string | null;
  api_id: number | null;
}

export interface Match {
  id: number;
  api_id: number | null;
  league: string;
  season: number | null;
  matchday: number | null;
  utc_date: string;
  status: 'SCHEDULED' | 'LIVE' | 'FINISHED' | 'POSTPONED';
  home_team: Team;
  away_team: Team;
  home_score: number | null;
  away_score: number | null;
  result: 'HOME' | 'DRAW' | 'AWAY' | null;
}

export interface MatchListResponse {
  total: number;
  items: Match[];
}

export interface Prediction {
  id: number;
  match_id: number;
  model_version: string;
  result_home: number | null;
  result_draw: number | null;
  result_away: number | null;
  btts: number | null;
  over_25: number | null;
  confidence: number | null;
  result_correct: boolean | null;
  btts_correct: boolean | null;
  over_25_correct: boolean | null;
  created_at: string;
}
