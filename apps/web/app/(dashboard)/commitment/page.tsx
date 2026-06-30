// SERVER — Commitment Check (§8.6). Pre-signature stress test → advisory verdict; the human
// signs. First-party only: the index move is an assumption, never an external feed.
import { CommitmentCheckForm } from "@/components/modules/commitment/commitment-check-form";
import { RequiresExternalDataBadge } from "@/components/RequiresExternalData";

export default function CommitmentCheckPage() {
  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-3">
        <h1 className="text-xl font-semibold">Commitment Check</h1>
        <span className="flex items-center gap-2 text-xs text-muted-foreground">
          market benchmarking <RequiresExternalDataBadge />
        </span>
      </div>
      <p className="text-sm text-muted-foreground">
        Stress-test a proposed (unsigned) deal&rsquo;s indexed exposure at &plusmn;5/10/15% and get
        an <strong>approve / condition / block</strong> verdict against your margin tolerance. The
        index move is a first-party assumption; the verdict is <strong>advisory</strong> &mdash;
        you sign, not the platform.
      </p>
      <CommitmentCheckForm />
    </div>
  );
}
