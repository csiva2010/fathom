import { NavLink, useNavigate } from "react-router-dom";

import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { Button } from "@/components/ui/Button";

import { useConversations, useDeleteConversation } from "../hooks/useConversations";

/** Start, switch and clear conversations (CH-07). */
export function ConversationSidebar({ activeId }: { activeId?: string }) {
  const conversations = useConversations();
  const remove = useDeleteConversation();
  const navigate = useNavigate();

  const onDelete = (id: string, title: string) => {
    if (!window.confirm(`Delete "${title}"? This can't be undone.`)) return;
    remove.mutate(id, {
      onSuccess: () => {
        if (id === activeId) navigate("/chat");
      },
    });
  };

  return (
    <aside aria-label="Conversations" className="flex min-h-0 flex-col gap-3">
      <Button onClick={() => navigate("/chat")} className="w-full">
        New chat
      </Button>
      {conversations.isPending && <LoadingState label="Loading conversations" />}
      {conversations.isError && (
        <ErrorState title="Couldn't load conversations" error={conversations.error} onRetry={() => void conversations.refetch()} />
      )}
      {conversations.data && conversations.data.conversations.length === 0 && (
        <p className="px-1 text-sm text-slate-500 dark:text-slate-400">No conversations yet.</p>
      )}
      {conversations.data && conversations.data.conversations.length > 0 && (
        <ul className="min-h-0 space-y-1 overflow-y-auto">
          {conversations.data.conversations.map((c) => (
            <li key={c.id} className="group flex items-center gap-1">
              <NavLink
                to={`/chat/${c.id}`}
                className={({ isActive }) =>
                  `min-w-0 flex-1 truncate rounded-md px-2 py-1.5 text-sm ${
                    isActive
                      ? "bg-emerald-50 font-medium text-emerald-900 dark:bg-emerald-900/40 dark:text-emerald-100"
                      : "text-slate-700 hover:bg-slate-100 dark:text-slate-200 dark:hover:bg-slate-800"
                  }`
                }
              >
                {c.title}
              </NavLink>
              <button
                type="button"
                onClick={() => onDelete(c.id, c.title)}
                aria-label={`Delete ${c.title}`}
                className="rounded p-1 text-slate-400 opacity-60 hover:bg-slate-100 hover:text-rose-700 group-hover:opacity-100 dark:hover:bg-slate-800"
              >
                ✕
              </button>
            </li>
          ))}
        </ul>
      )}
    </aside>
  );
}
