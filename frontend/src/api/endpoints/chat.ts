import { API_PREFIX, ApiError, apiFetch, toApiError } from "../client";
import { readEventStream } from "../sse";
import type { ChatEvent, Conversation, ConversationDetail, ConversationList, MessageCreate } from "../types";

export function listConversations(): Promise<ConversationList> {
  return apiFetch<ConversationList>("/conversations");
}

export function createConversation(): Promise<Conversation> {
  return apiFetch<Conversation>("/conversations", { method: "POST", body: JSON.stringify({}) });
}

export function getConversation(id: string): Promise<ConversationDetail> {
  return apiFetch<ConversationDetail>(`/conversations/${encodeURIComponent(id)}`);
}

export async function deleteConversation(id: string): Promise<void> {
  await apiFetch<undefined>(`/conversations/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/**
 * Send a message, optionally with a portfolio screenshot (CH-09), and stream the answer
 * (CH-01). Validation errors (unknown conversation, message too long, bad image) reject
 * before any event; failures mid-answer arrive as an `error` event.
 */
export async function streamMessage(
  conversationId: string,
  message: MessageCreate,
  onEvent: (event: ChatEvent) => void,
  signal?: AbortSignal,
): Promise<void> {
  let response: Response;
  try {
    response = await fetch(`${API_PREFIX}/conversations/${encodeURIComponent(conversationId)}/messages`, {
      method: "POST",
      credentials: "same-origin",
      headers: { Accept: "text/event-stream", "Content-Type": "application/json" },
      body: JSON.stringify(message),
      signal,
    });
  } catch (error) {
    if (signal?.aborted) throw error;
    throw new ApiError(0, "network_error", "Can't reach the server. Check your connection.", true);
  }
  if (!response.ok) throw await toApiError(response);
  if (!response.body) throw new ApiError(response.status, "empty_stream", "The answer stream was empty.", true);
  await readEventStream(response.body, (data) => onEvent(data as ChatEvent));
}
