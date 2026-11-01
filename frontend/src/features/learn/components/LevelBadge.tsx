import { LEVEL_STYLES } from "../levels";

export function LevelBadge({ level }: { level: string }) {
  return (
    <span className={`rounded-full px-2 py-0.5 text-xs font-medium capitalize ${LEVEL_STYLES[level] ?? "bg-slate-100 text-slate-700"}`}>
      {level}
    </span>
  );
}
