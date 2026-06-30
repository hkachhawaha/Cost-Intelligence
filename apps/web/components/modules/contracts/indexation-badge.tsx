// SERVER. Surfaces CPI/escalation exposure on a contract (Phase 7 deepens this).
export function IndexationBadge({
  indexation,
}: {
  indexation: { index_type: string | null; indexed_share: string };
}) {
  return (
    <span className="rounded-full bg-[hsl(var(--terzo-control))]/15 px-2 py-0.5 text-xs text-[hsl(var(--terzo-control))]">
      {indexation.index_type ?? "Indexed"} · {Number(indexation.indexed_share) * 100}%
    </span>
  );
}
