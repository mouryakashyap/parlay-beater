import { useQuery } from "@tanstack/react-query";
import { fetchUpcomingMatches } from "../api/client";

export default function Dashboard() {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["upcoming-matches"],
    queryFn: () => fetchUpcomingMatches(),
  });

  if (isLoading) return <p className="text-gray-400">Loading matches...</p>;
  if (isError)   return <p className="text-red-400">Failed to load matches.</p>;

  return (
    <div>
      <h1 className="text-2xl font-bold mb-6">Upcoming Matches</h1>
      {data?.items?.length === 0 && (
        <p className="text-gray-400">No upcoming matches found. Run data ingestion first.</p>
      )}
      <div className="space-y-3">
        {data?.items?.map((match: any) => (
          <div key={match.id} className="bg-gray-900 border border-gray-800 rounded-lg p-4 flex justify-between items-center">
            <div className="flex gap-6 items-center">
              <span className="font-medium">{match.home_team.name}</span>
              <span className="text-gray-500 text-sm">vs</span>
              <span className="font-medium">{match.away_team.name}</span>
            </div>
            <div className="text-right text-sm text-gray-400">
              <p>{match.league}</p>
              <p>{new Date(match.utc_date).toLocaleDateString()}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
