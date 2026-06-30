"use client";

// Minimal owner picker. The candidate list comes from the team roster in a later
// iteration; for v1 it's a free-form select wired to PATCH /assign.
const PLACEHOLDER_OWNERS = [
  { id: "", label: "Unassigned" },
  { id: "00000000-0000-0000-0000-000000000001", label: "Procurement" },
  { id: "00000000-0000-0000-0000-000000000002", label: "Finance" },
];

export function OwnerSelect({
  value,
  onChange,
}: {
  value?: string | null;
  onChange: (ownerId: string) => void;
}) {
  return (
    <select
      value={value ?? ""}
      onChange={(e) => onChange(e.target.value)}
      aria-label="Assign owner"
      className="rounded-md border bg-transparent px-2 py-1 text-sm"
    >
      {PLACEHOLDER_OWNERS.map((o) => (
        <option key={o.id} value={o.id}>
          {o.label}
        </option>
      ))}
    </select>
  );
}
