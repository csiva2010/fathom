import type { AgentName, Artifact, ChatEvent, ChatMessage, Citation, Freshness, TraceStep } from "@/api/types";

/** The answer being streamed, built up from chat events. */
export interface DraftAnswer {
  status: "routing" | "streaming" | "done" | "error";
  kind: ChatMessage["kind"];
  agents: AgentName[];
  content: string;
  artifacts: Artifact[];
  citations: Citation[];
  freshness: Freshness[];
  followUps: string[];
  trace: TraceStep[];
  error?: { message: string; retryable: boolean };
}

export function emptyDraft(): DraftAnswer {
  return {
    status: "routing",
    kind: "answer",
    agents: [],
    content: "",
    artifacts: [],
    citations: [],
    freshness: [],
    followUps: [],
    trace: [],
  };
}

/** Fold one SSE event into the draft. `done` carries the authoritative final message. */
export function applyEvent(draft: DraftAnswer, event: ChatEvent): DraftAnswer {
  switch (event.type) {
    case "route":
      return { ...draft, status: "streaming", kind: event.kind, agents: event.agents };
    case "agent_start":
      return draft;
    case "trace":
      return { ...draft, trace: [...draft.trace, event.step] };
    case "token":
      return { ...draft, status: "streaming", content: draft.content + event.text };
    case "replace":
      return { ...draft, content: event.text };
    case "artifact":
      return { ...draft, artifacts: [...draft.artifacts, event.artifact] };
    case "citation":
      return { ...draft, citations: [...draft.citations, event.citation] };
    case "freshness":
      return { ...draft, freshness: [...draft.freshness, event.freshness] };
    case "done":
      return { ...draftFromMessage(event.message), status: "done" };
    case "error":
      return { ...draft, status: "error", error: { message: event.message, retryable: event.retryable ?? false } };
  }
}

export function draftFromMessage(message: ChatMessage): DraftAnswer {
  return {
    status: "done",
    kind: message.kind,
    agents: message.agents ?? [],
    content: message.content,
    artifacts: message.artifacts ?? [],
    citations: message.citations ?? [],
    freshness: message.freshness ?? [],
    followUps: message.follow_ups ?? [],
    trace: message.trace ?? [],
  };
}
