interface Props {
  confidence: number | null;
}

export default function ConfidenceBadge({ confidence }: Props) {
  if (confidence === null) return <span className="text-xs text-gray-600">—</span>;
  const pct = Math.round(confidence * 100);
  const { label, cls } =
    pct >= 70
      ? { label: 'HIGH', cls: 'bg-green-900 text-green-300 border-green-800' }
      : pct >= 50
        ? { label: 'MED',  cls: 'bg-yellow-900 text-yellow-300 border-yellow-800' }
        : { label: 'LOW',  cls: 'bg-red-900 text-red-300 border-red-800' };

  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded border text-xs font-bold ${cls}`}>
      {label} <span className="font-normal opacity-75">{pct}%</span>
    </span>
  );
}
