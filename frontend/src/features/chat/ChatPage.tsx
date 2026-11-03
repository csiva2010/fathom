import { useEffect, useRef } from "react";
import { useParams, useSearchParams } from "react-router-dom";

import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";

import { AssistantMessage } from "./components/AssistantMessage";
import { Composer } from "./components/Composer";
import { ConversationSidebar } from "./components/ConversationSidebar";
import { UserMessage } from "./components/UserMessage";
import type { Attachment } from "./attachments";
import { draftFromMessage } from "./hooks/chatState";
import { useChat } from "./hooks/useChat";
import { useConversation } from "./hooks/useConversations";

const STARTERS = [
  "What is an index fund?",
  "How is the market doing today?",
  "How does a Roth IRA differ from a traditional IRA?",
  "I want $40,000 for a house by 2030. Am I on track saving $500 a month?",
];

const SCREENSHOT_TIP = "Tip: paste or attach a screenshot of your brokerage holdings to have them analyzed.";

function Welcome({ onAsk }: { onAsk: (q: string) => void }) {
  return (
    <div className="mx-auto max-w-xl space-y-4 py-10 text-center">
      <h2 className="text-lg font-semibold">What would you like to understand today?</h2>
      <p className="text-sm text-slate-600 dark:text-slate-300">
        Ask about investing concepts, market data, your portfolio, savings goals, news or taxes. Answers explain; they
        never tell you what to buy or sell.
      </p>
      <p className="text-xs text-slate-500 dark:text-slate-400">{SCREENSHOT_TIP}</p>
      <div className="grid gap-2 sm:grid-cols-2">
        {STARTERS.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => onAsk(q)}
            className="rounded-lg border border-slate-200 p-3 text-left text-sm hover:border-emerald-600 dark:border-slate-700 dark:hover:border-emerald-400"
          >
            {q}
          </button>
        ))}
      </div>
    </div>
  );
}

/** The Chat tab: conversation list, streamed answers and the composer (CH-01 to CH-07). */
export function ChatPage() {
  const { conversationId } = useParams();
  // "Ask Fathom about this" on an article opens /chat?ask=...: the question waits in the
  // composer so the user can edit it before sending.
  const [params] = useSearchParams();
  const handedOver = params.get("ask") ?? "";
  const conversation = useConversation(conversationId);
  const chat = useChat(conversationId);
  const endRef = useRef<HTMLDivElement>(null);

  const messages = conversation.data?.messages ?? [];
  const ask = (question: string, image?: Attachment) => void chat.send(question, image);
  const lastAnswerId = [...messages].reverse().find((m) => m.role === "assistant")?.id;

  useEffect(() => {
    endRef.current?.scrollIntoView?.({ block: "end" });
  }, [messages.length, chat.pending?.answer.content, chat.pending?.answer.artifacts.length]);

  const showWelcome = !conversationId && !chat.pending;

  return (
    <div className="grid gap-4 md:h-[calc(100dvh-10.5rem)] md:grid-cols-[15rem_1fr]">
      <ConversationSidebar activeId={conversationId} />
      <section aria-label="Chat" className="flex min-h-[60vh] min-w-0 flex-col gap-3">
        <div className="min-h-0 flex-1 space-y-6 overflow-y-auto pr-1">
          {showWelcome && <Welcome onAsk={ask} />}
          {conversationId && conversation.isPending && !chat.pending && <LoadingState label="Loading conversation" />}
          {conversation.isError && (
            <ErrorState title="Couldn't load this conversation" error={conversation.error} onRetry={() => void conversation.refetch()} />
          )}
          {messages.map((message) =>
            message.role === "user" ? (
              <UserMessage key={message.id} content={message.content} hasImage={message.has_image} />
            ) : (
              <AssistantMessage
                key={message.id}
                id={message.id}
                answer={draftFromMessage(message)}
                onAsk={message.id === lastAnswerId && !chat.pending ? ask : undefined}
                busy={chat.isStreaming}
              />
            ),
          )}
          {chat.pending && (
            <>
              <UserMessage content={chat.pending.question} imageUrl={chat.pending.image?.previewUrl} />
              <AssistantMessage
                id="pending"
                answer={chat.pending.answer}
                onRetry={() => {
                  const question = chat.pending?.question ?? "";
                  const image = chat.pending?.image;
                  chat.dismiss();
                  ask(question, image);
                }}
              />
            </>
          )}
          <div ref={endRef} />
        </div>
        <Composer key={handedOver} initialText={handedOver} onSend={ask} onStop={chat.stop} streaming={chat.isStreaming} />
      </section>
    </div>
  );
}
