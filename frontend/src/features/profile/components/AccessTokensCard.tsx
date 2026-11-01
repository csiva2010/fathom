import { useState, type FormEvent } from "react";

import { API_PREFIX } from "@/api/client";
import type { ApiTokenCreated } from "@/api/types";
import { ErrorState } from "@/components/feedback/ErrorState";
import { LoadingState } from "@/components/feedback/LoadingState";
import { Button } from "@/components/ui/Button";
import { INPUT_CLASS, LABEL_CLASS } from "@/components/ui/styles";
import { timeAgo } from "@/lib/format/time";

import { claudeDesktopConfig } from "../claudeDesktopConfig";
import { useAccessTokens, useCreateToken, useRevokeToken } from "../hooks/useAccessTokens";

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);
  const copy = () => {
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  };
  return (
    <Button variant="secondary" className="px-3 py-1 text-xs" onClick={copy} aria-label={label}>
      {copied ? "Copied" : "Copy"}
    </Button>
  );
}

function NewToken({ created, onDone }: { created: ApiTokenCreated; onDone: () => void }) {
  const config = claudeDesktopConfig(created.token, `${window.location.origin}${API_PREFIX}`);
  return (
    <div className="space-y-3 rounded-lg border border-emerald-300 bg-emerald-50 p-4 text-sm dark:border-emerald-800 dark:bg-emerald-950/40">
      <p className="font-medium text-emerald-900 dark:text-emerald-200">
        Copy your token now. You won't be able to see it again.
      </p>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded bg-white px-2 py-1 font-mono text-xs dark:bg-slate-900">
          {created.token}
        </code>
        <CopyButton text={created.token} label="Copy token" />
      </div>
      <div>
        <div className="mb-1 flex items-center justify-between gap-2">
          <p className="text-xs text-slate-700 dark:text-slate-300">
            Claude Desktop config (Settings → Developer → Edit Config). Replace both{" "}
            <code>/path/to/fathom/backend</code> paths with your checkout.
          </p>
          <CopyButton text={config} label="Copy Claude Desktop config" />
        </div>
        <pre className="overflow-x-auto rounded bg-white p-3 font-mono text-xs dark:bg-slate-900">{config}</pre>
      </div>
      <Button variant="secondary" onClick={onDone}>
        Done
      </Button>
    </div>
  );
}

/** Personal access tokens that let the MCP server call this API as the user (MCP-03). */
export function AccessTokensCard() {
  const tokens = useAccessTokens();
  const create = useCreateToken();
  const revoke = useRevokeToken();
  const [name, setName] = useState("Claude Desktop");
  const [created, setCreated] = useState<ApiTokenCreated | null>(null);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    create.mutate(name.trim(), { onSuccess: setCreated });
  };

  return (
    <section aria-labelledby="tokens-heading" className="space-y-4 rounded-xl border border-slate-200 p-5 dark:border-slate-800 lg:col-span-2">
      <div>
        <h2 id="tokens-heading" className="font-medium">
          Claude Desktop access
        </h2>
        <p className="mt-1 text-sm text-slate-600 dark:text-slate-300">
          A personal access token lets the app's MCP server answer questions in Claude Desktop with your portfolios,
          goals and the same market data and articles. Treat it like a password and revoke it if it leaks.
        </p>
      </div>

      {created ? (
        <NewToken created={created} onDone={() => setCreated(null)} />
      ) : (
        <form onSubmit={submit} className="flex flex-wrap items-end gap-2">
          <div className="min-w-48 flex-1">
            <label htmlFor="token-name" className={LABEL_CLASS}>
              Token name
            </label>
            <input
              id="token-name"
              className={INPUT_CLASS}
              value={name}
              maxLength={120}
              onChange={(e) => setName(e.target.value)}
            />
          </div>
          <Button type="submit" disabled={!name.trim() || create.isPending}>
            {create.isPending ? "Creating…" : "Create token"}
          </Button>
        </form>
      )}
      {create.isError && <ErrorState title="Couldn't create the token" error={create.error} />}

      {tokens.isPending && <LoadingState label="Loading tokens" />}
      {tokens.isError && (
        <ErrorState title="Couldn't load your tokens" error={tokens.error} onRetry={() => void tokens.refetch()} />
      )}
      {tokens.data && tokens.data.tokens.length === 0 && (
        <p className="text-sm text-slate-500 dark:text-slate-400">No active tokens.</p>
      )}
      {tokens.data && tokens.data.tokens.length > 0 && (
        <ul className="divide-y divide-slate-100 text-sm dark:divide-slate-800">
          {tokens.data.tokens.map((token) => (
            <li key={token.id} className="flex items-center justify-between gap-4 py-2">
              <div>
                <p className="font-medium">{token.name}</p>
                <p className="text-xs text-slate-500 dark:text-slate-400">
                  Created {timeAgo(token.created_at)} ·{" "}
                  {token.last_used_at ? `last used ${timeAgo(token.last_used_at)}` : "never used"}
                </p>
              </div>
              <Button
                variant="ghost"
                className="text-rose-700 dark:text-rose-400"
                disabled={revoke.isPending}
                onClick={() => revoke.mutate(token.id)}
                aria-label={`Revoke ${token.name}`}
              >
                Revoke
              </Button>
            </li>
          ))}
        </ul>
      )}
      {revoke.isError && <ErrorState title="Couldn't revoke the token" error={revoke.error} />}
    </section>
  );
}
