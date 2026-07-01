import { apiFetch } from "@/lib/api";

interface LlmProvider {
  name: string;
  active: boolean;
  status: string;
  models: {
    alias: string;
    model: string;
    useCase: string;
    costPerMillion: { input: string; output: string };
  }[];
}

export default async function LlmProvidersPage() {
  let providers: LlmProvider[] = [];
  let error: string | null = null;
  try {
    const res = await apiFetch<{ providers: LlmProvider[] }>("/ci/settings/llm-providers");
    providers = res.providers;
  } catch (e) {
    error = e instanceof Error ? e.message : "Failed to load LLM providers";
  }

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">LLM Provider Settings</h1>
        <p className="mt-1 text-sm text-slate-500">
          Active foundation model configurations mapped in the Model Gateway.
        </p>
      </header>

      {error && (
        <div className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-700">
          {error}
        </div>
      )}

      {providers.map((provider) => (
        <div key={provider.name} className="rounded-lg border p-6 bg-white shadow-sm space-y-4">
          <div className="flex items-center gap-3">
            <h2 className="text-lg font-bold text-slate-900">{provider.name}</h2>
            <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${provider.active ? "bg-green-100 text-green-800" : "bg-yellow-100 text-yellow-800"}`}>
              {provider.status}
            </span>
          </div>

          <div className="overflow-x-auto">
            <table className="min-w-full divide-y divide-slate-200">
              <thead>
                <tr>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase">Alias</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase">Model Pinned</th>
                  <th className="px-3 py-2 text-left text-xs font-semibold text-slate-500 uppercase">Use Case</th>
                  <th className="px-3 py-2 text-right text-xs font-semibold text-slate-500 uppercase">Cost / 1M Input</th>
                  <th className="px-3 py-2 text-right text-xs font-semibold text-slate-500 uppercase">Cost / 1M Output</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-200">
                {provider.models.map((m) => (
                  <tr key={m.alias} className="text-sm">
                    <td className="px-3 py-2.5 font-medium text-slate-900">{m.alias}</td>
                    <td className="px-3 py-2.5 font-mono text-indigo-600">{m.model}</td>
                    <td className="px-3 py-2.5 text-slate-600">{m.useCase}</td>
                    <td className="px-3 py-2.5 text-right font-medium text-slate-900">{m.costPerMillion.input}</td>
                    <td className="px-3 py-2.5 text-right font-medium text-slate-900">{m.costPerMillion.output}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      ))}
    </section>
  );
}
