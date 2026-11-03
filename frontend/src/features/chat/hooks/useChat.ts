import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { createConversation, streamMessage } from "@/api/endpoints/chat";
import { queryKeys } from "@/api/queryKeys";
import type { ChatMessage, ConversationDetail } from "@/api/types";

import { SCREENSHOT_QUESTION, toImageAttachment, type Attachment } from "../attachments";
import { applyEvent, emptyDraft, type DraftAnswer } from "./chatState";

export interface PendingTurn {
  question: string;
  image?: Attachment; // kept in memory only, so the preview shows and a retry can resend it
  answer: DraftAnswer;
}

/**
 * Sends messages and tracks the answer being streamed (CH-01). A new chat creates its
 * conversation on the first message. When the answer is done it moves into the cached
 * conversation in the same render the draft disappears, so nothing flickers.
 */
export function useChat(conversationId: string | undefined) {
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [pending, setPending] = useState<PendingTurn | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const streamingIdRef = useRef<string | undefined>(undefined);

  // Leaving for another conversation stops the stream; the server still finishes the turn.
  useEffect(() => {
    if (abortRef.current && streamingIdRef.current !== conversationId) {
      abortRef.current.abort();
      abortRef.current = null;
      setPending(null);
    }
  }, [conversationId]);
  useEffect(() => () => abortRef.current?.abort(), []);

  const isStreaming = pending !== null && (pending.answer.status === "routing" || pending.answer.status === "streaming");

  const send = useCallback(
    async (text: string, image?: Attachment) => {
      const question = text.trim() || (image ? SCREENSHOT_QUESTION : "");
      if (!question || abortRef.current) return;
      const controller = new AbortController();
      abortRef.current = controller;
      setPending({ question, image, answer: emptyDraft() });

      let id = conversationId;
      let final: ChatMessage | undefined;
      try {
        if (!id) {
          id = (await createConversation()).id;
          streamingIdRef.current = id;
          navigate(`/chat/${id}`);
        }
        streamingIdRef.current = id;
        await streamMessage(
          id,
          { content: question, image: image ? toImageAttachment(image) : null },
          (event) => {
            if (event.type === "done") final = event.message;
            setPending((turn) => turn && { ...turn, answer: applyEvent(turn.answer, event) });
          },
          controller.signal,
        );
        if (final) {
          const key = queryKeys.conversation(id);
          const asked: ChatMessage = {
            id: `${final.id}-q`,
            role: "user",
            content: question,
            kind: "answer",
            has_image: Boolean(image),
          };
          const answered = final;
          const updated = queryClient.setQueryData<ConversationDetail>(
            key,
            (old) => old && { ...old, messages: [...old.messages, asked, answered] },
          );
          if (!updated) await queryClient.invalidateQueries({ queryKey: key });
          setPending(null);
        } else {
          // The stream ended without `done`: either an `error` event (already shown) or a drop.
          setPending(
            (turn) =>
              turn &&
              (turn.answer.status === "error"
                ? turn
                : {
                    ...turn,
                    answer: {
                      ...turn.answer,
                      status: "error",
                      error: { message: "The connection closed before the answer finished.", retryable: true },
                    },
                  }),
          );
        }
      } catch (error) {
        if (!controller.signal.aborted) {
          const message = error instanceof Error ? error.message : "Something went wrong. Please try again.";
          setPending(
            (turn) => turn && { ...turn, answer: { ...turn.answer, status: "error", error: { message, retryable: true } } },
          );
        }
      } finally {
        if (abortRef.current === controller) abortRef.current = null;
        void queryClient.invalidateQueries({ queryKey: queryKeys.conversations, exact: true });
      }
    },
    [conversationId, navigate, queryClient],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setPending(null);
  }, []);

  const dismiss = useCallback(() => setPending(null), []);

  return { pending, isStreaming, send, stop, dismiss };
}
