import { useRef, useState, type ChangeEvent, type FormEvent } from "react";

import type { AssetClass, PortfolioOut } from "@/api/types";
import { ErrorState } from "@/components/feedback/ErrorState";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { INPUT_CLASS, LABEL_CLASS } from "@/components/ui/styles";

import { ASSET_CLASSES } from "../assetClasses";
import { useImportCsv, useSavePortfolio } from "../hooks/usePortfolios";

interface Row {
  key: number;
  symbol: string;
  quantity: string;
  cost: string;
  assetClass: AssetClass | "";
}

let nextKey = 1;
const emptyRow = (): Row => ({ key: nextKey++, symbol: "", quantity: "", cost: "", assetClass: "" });

/**
 * PF-01: build a portfolio by hand or from a CSV. Imported rows land in the form for
 * review; nothing is saved until the user presses Save. Samples are saved as a copy.
 */
export function PortfolioEditor({ portfolio, onDone }: { portfolio?: PortfolioOut; onDone: (saved?: PortfolioOut) => void }) {
  const copying = portfolio?.is_sample ?? false;
  const save = useSavePortfolio();
  const csv = useImportCsv();
  const fileRef = useRef<HTMLInputElement>(null);
  const [name, setName] = useState(portfolio ? (copying ? `${portfolio.name} (my copy)` : portfolio.name) : "");
  const [rows, setRows] = useState<Row[]>(
    portfolio?.holdings.length
      ? portfolio.holdings.map((h) => ({
          key: nextKey++,
          symbol: h.symbol,
          quantity: String(h.quantity),
          cost: h.cost_basis == null ? "" : String(h.cost_basis),
          assetClass: h.asset_class ?? "",
        }))
      : [emptyRow(), emptyRow(), emptyRow()],
  );

  const change = (key: number, field: keyof Omit<Row, "key">, value: string) =>
    setRows((prev) => prev.map((r) => (r.key === key ? { ...r, [field]: value } : r)));

  const onFile = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file) return;
    if (file.size > 1_000_000) {
      csv.reset();
      window.alert("That file is larger than 1 MB.");
      return;
    }
    const parsed = await csv.mutateAsync(await file.text()).catch(() => null);
    if (parsed && parsed.holdings.length > 0) {
      setRows(
        parsed.holdings.map((h) => ({
          key: nextKey++,
          symbol: h.symbol,
          quantity: String(h.quantity),
          cost: h.cost_basis == null ? "" : String(h.cost_basis),
          assetClass: h.asset_class ?? "",
        })),
      );
    }
  };

  const filled = rows.filter((r) => r.symbol.trim() || r.quantity.trim());
  const onSubmit = (event: FormEvent) => {
    event.preventDefault();
    save.mutate(
      {
        id: copying ? undefined : portfolio?.id,
        body: {
          name: name.trim(),
          description: portfolio?.description ?? "",
          holdings: filled.map((r) => ({
            symbol: r.symbol.trim().toUpperCase(),
            quantity: Number(r.quantity),
            cost_basis: r.cost.trim() ? Number(r.cost) : null,
            asset_class: r.assetClass || null,
          })),
        },
      },
      { onSuccess: (saved) => onDone(saved) },
    );
  };

  return (
    <Card title={portfolio && !copying ? "Edit portfolio" : copying ? "Save a copy to edit" : "New portfolio"}>
      <form onSubmit={onSubmit} className="space-y-4">
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-56 flex-1">
            <label htmlFor="portfolio-name" className={LABEL_CLASS}>
              Name
            </label>
            <input id="portfolio-name" required maxLength={120} value={name} onChange={(e) => setName(e.target.value)} className={INPUT_CLASS} />
          </div>
          <div>
            <input ref={fileRef} type="file" accept=".csv,text/csv" className="sr-only" onChange={(e) => void onFile(e)} aria-label="CSV file" />
            <Button variant="secondary" onClick={() => fileRef.current?.click()} disabled={csv.isPending}>
              {csv.isPending ? "Reading…" : "Import CSV"}
            </Button>
          </div>
        </div>
        <p className="text-xs text-slate-500 dark:text-slate-400">
          CSV needs a header row with symbol and quantity columns; cost basis (per share) and asset class are optional. Up to
          200 rows.
        </p>
        {csv.isError && <ErrorState title="Couldn't read that file" error={csv.error} />}
        {csv.data && csv.data.errors.length > 0 && (
          <div role="alert" className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-200">
            <p className="font-medium">
              Imported {csv.data.holdings.length} row{csv.data.holdings.length === 1 ? "" : "s"}; some lines need attention:
            </p>
            <ul className="mt-1 list-disc pl-5">
              {csv.data.errors.map((e) => (
                <li key={e}>{e}</li>
              ))}
            </ul>
          </div>
        )}

        <div className="overflow-x-auto">
          <table className="w-full min-w-[34rem] text-sm">
            <thead className="text-left text-xs text-slate-500 dark:text-slate-400">
              <tr>
                <th className="pb-1 font-medium">Ticker</th>
                <th className="pb-1 font-medium">Shares</th>
                <th className="pb-1 font-medium">Cost per share ($, optional)</th>
                <th className="pb-1 font-medium">Asset class</th>
                <th className="pb-1">
                  <span className="sr-only">Remove</span>
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r, i) => (
                <tr key={r.key}>
                  <td className="py-1 pr-2">
                    <input aria-label={`Ticker ${i + 1}`} value={r.symbol} maxLength={10} onChange={(e) => change(r.key, "symbol", e.target.value)} className={`${INPUT_CLASS} uppercase`} placeholder="VTI" />
                  </td>
                  <td className="py-1 pr-2">
                    <input aria-label={`Shares ${i + 1}`} type="number" min={0} step="any" value={r.quantity} onChange={(e) => change(r.key, "quantity", e.target.value)} className={INPUT_CLASS} required={Boolean(r.symbol.trim())} />
                  </td>
                  <td className="py-1 pr-2">
                    <input aria-label={`Cost per share ${i + 1}`} type="number" min={0} step="any" value={r.cost} onChange={(e) => change(r.key, "cost", e.target.value)} className={INPUT_CLASS} />
                  </td>
                  <td className="py-1 pr-2">
                    <select aria-label={`Asset class ${i + 1}`} value={r.assetClass} onChange={(e) => change(r.key, "assetClass", e.target.value)} className={INPUT_CLASS}>
                      <option value="">Detect</option>
                      {ASSET_CLASSES.map((c) => (
                        <option key={c.value} value={c.value}>
                          {c.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td className="py-1">
                    <button
                      type="button"
                      aria-label={`Remove row ${i + 1}`}
                      onClick={() => setRows((prev) => (prev.length > 1 ? prev.filter((x) => x.key !== r.key) : [emptyRow()]))}
                      className="rounded p-1 text-slate-400 hover:text-rose-700"
                    >
                      ✕
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <Button variant="ghost" onClick={() => setRows((prev) => [...prev, emptyRow()])} disabled={rows.length >= 200}>
          + Add holding
        </Button>
        {save.isError && <ErrorState title="Couldn't save the portfolio" error={save.error} />}
        <div className="flex gap-2">
          <Button type="submit" disabled={save.isPending || !name.trim() || filled.length === 0}>
            {save.isPending ? "Saving…" : "Save portfolio"}
          </Button>
          <Button variant="ghost" onClick={() => onDone()}>
            Cancel
          </Button>
        </div>
      </form>
    </Card>
  );
}
