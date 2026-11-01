/** Fathom's mark: a sounding line dropped below the surface to measure depth. */
export function LogoMark({ className = "h-7 w-7" }: { className?: string }) {
  return <img src="/favicon.svg" alt="" aria-hidden className={className} />;
}

export function Logo() {
  return (
    <span className="flex items-center gap-2">
      <LogoMark />
      <span className="text-lg font-semibold tracking-tight text-slate-900 dark:text-white">Fathom</span>
    </span>
  );
}
