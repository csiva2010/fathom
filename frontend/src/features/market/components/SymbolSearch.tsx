import { useState } from "react";

import { INPUT_CLASS } from "@/components/ui/styles";
import { useDebounced } from "@/lib/hooks/useDebounced";

import { useSymbolSearch } from "../hooks/useMarketData";

/** Ticker search (MD-09); picking a result calls `onPick`. */
export function SymbolSearch({ onPick }: { onPick: (symbol: string) => void }) {
  const [q, setQ] = useState("");
  const search = useSymbolSearch(useDebounced(q.trim(), 200));
  const results = q.trim() ? (search.data?.results ?? []) : [];

  return (
    <div className="relative">
      <label htmlFor="symbol-search" className="sr-only">
        Add a ticker
      </label>
      <input
        id="symbol-search"
        type="search"
        value={q}
        onChange={(e) => setQ(e.target.value)}
        placeholder="Add a ticker or company"
        autoComplete="off"
        className={INPUT_CLASS}
      />
      {q.trim() && (
        <ul
          aria-label="Search results"
          className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-lg border border-slate-200 bg-white text-sm shadow-lg dark:border-slate-700 dark:bg-slate-900"
        >
          {search.isFetching && results.length === 0 && <li className="px-3 py-2 text-slate-500">Searching…</li>}
          {search.isError && <li className="px-3 py-2 text-rose-700">{search.error.message}</li>}
          {!search.isFetching && search.data && results.length === 0 && <li className="px-3 py-2 text-slate-500">No US stocks or ETFs match.</li>}
          {results.map((r) => (
            <li key={r.symbol}>
              <button
                type="button"
                aria-label={r.name ? `${r.symbol}, ${r.name}` : r.symbol}
                onClick={() => {
                  onPick(r.symbol);
                  setQ("");
                }}
                className="flex w-full gap-2 px-3 py-2 text-left hover:bg-slate-100 dark:hover:bg-slate-800"
              >
                <span className="w-16 font-semibold">{r.symbol}</span>
                <span className="truncate text-slate-600 dark:text-slate-300">{r.name}</span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
