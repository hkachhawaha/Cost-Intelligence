import { useMutation } from "@tanstack/react-query";

import { apiClient } from "@/lib/api";
import type { NirvanaChatResponse, NirvanaDraft } from "@/lib/types";

// Chat uses the JSON fallback (Accept: application/json) for a simple request/response;
// SSE token streaming is a progressive enhancement layered on the same endpoint.
export function useNirvanaChat() {
  return useMutation({
    mutationFn: (vars: { message: string; conversation_id?: string; module_context?: string }) =>
      apiClient.post<NirvanaChatResponse>("/nirvana/chat", vars),
  });
}

export function useGenerateDoc() {
  return useMutation({
    mutationFn: (vars: {
      template: string;
      context: { type: "opportunity" | "contract" | "vendor"; id: string };
      conversation_id?: string;
    }) => apiClient.post<NirvanaDraft>("/nirvana/generate-doc", vars),
  });
}
