export default function CostBreakdownPage() {
  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Operational Cost Breakdown</h1>
        <p className="mt-1 text-sm text-slate-500">
          Detailed monthly cost breakdown of the current Supabase + Render production hosting environment.
        </p>
      </header>

      <div className="rounded-lg border bg-white shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-slate-200">
            <thead>
              <tr className="bg-slate-50">
                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Service Provider</th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Component</th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Tier / Size</th>
                <th className="px-6 py-3 text-right text-xs font-semibold text-slate-500 uppercase">Estimated Monthly Cost</th>
                <th className="px-6 py-3 text-left text-xs font-semibold text-slate-500 uppercase">Notes</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-200 text-sm text-slate-700">
              <tr>
                <td className="px-6 py-4 font-semibold text-slate-900">Vercel</td>
                <td className="px-6 py-4">Next.js Frontend</td>
                <td className="px-6 py-4">Pro Plan</td>
                <td className="px-6 py-4 text-right font-bold text-slate-900">$20.00</td>
                <td className="px-6 py-4 text-slate-500">Team collabs, previews, global Edge CDN</td>
              </tr>
              <tr>
                <td className="px-6 py-4 font-semibold text-slate-900">Render</td>
                <td className="px-6 py-4">FastAPI Backend + Worker</td>
                <td className="px-6 py-4">Starter (512MB RAM, 0.5 CPU)</td>
                <td className="px-6 py-4 text-right font-bold text-slate-900">$7.00</td>
                <td className="px-6 py-4 text-slate-500">API + Celery concurrency in 1 container</td>
              </tr>
              <tr>
                <td className="px-6 py-4 font-semibold text-slate-900">Supabase</td>
                <td className="px-6 py-4">Database & Auth</td>
                <td className="px-6 py-4">Free Tier</td>
                <td className="px-6 py-4 text-right font-bold text-slate-900">$0.00</td>
                <td className="px-6 py-4 text-slate-500">Managed Postgres (pgvector) + GoTrue Auth</td>
              </tr>
              <tr>
                <td className="px-6 py-4 font-semibold text-slate-900">Upstash</td>
                <td className="px-6 py-4">Redis Cache</td>
                <td className="px-6 py-4">Serverless Free Tier</td>
                <td className="px-6 py-4 text-right font-bold text-slate-900">$0.00</td>
                <td className="px-6 py-4 text-slate-500">Transient celery queue broker & cache</td>
              </tr>
              <tr>
                <td className="px-6 py-4 font-semibold text-slate-900">Google Gemini</td>
                <td className="px-6 py-4">Gemini API</td>
                <td className="px-6 py-4">Pay-as-you-go</td>
                <td className="px-6 py-4 text-right font-bold text-slate-900">$15.00</td>
                <td className="px-6 py-4 text-slate-500">Attributed model token usage</td>
              </tr>
              <tr className="bg-slate-50 border-t-2 border-slate-200 text-slate-900">
                <td colSpan={3} className="px-6 py-4 font-extrabold text-base">Total Monthly Estimated Cost</td>
                <td className="px-6 py-4 text-right font-extrabold text-base text-green-600">$42.00</td>
                <td className="px-6 py-4 font-semibold text-slate-500">Highly optimized Supabase stack savings ($30 saved)</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </section>
  );
}
