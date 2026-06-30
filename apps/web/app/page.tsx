import { redirect } from "next/navigation";

// Root route → the Cost Intelligence app (single-workspace, Google-Sheets-driven).
export default function Home() {
  redirect("/ci");
}
