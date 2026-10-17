import Link from "next/link";

import { ThemeToggle } from "./ThemeToggle";

export function Wordmark() {
  return (
    <Link href="/" className="wordmark" aria-label="Knockout, home">
      knockout<span className="wordmark-genotype" aria-hidden="true">−/−</span>
    </Link>
  );
}

export function RunningHeader({
  current,
  sourceState,
}: {
  current?: string;
  sourceState?: { state: "live" | "fixture" | "offline" | "pending"; label: string };
}) {
  return (
    <header className="running-header">
      <div className="running-header-inner">
        <Wordmark />
        {current ? (
          <nav className="running-header-trail" aria-label="Breadcrumb">
            <span className="divider" aria-hidden="true">/</span>
            <span>Report</span>
            <span className="divider" aria-hidden="true">/</span>
            <span className="current" aria-current="page">{current}</span>
          </nav>
        ) : null}
        <div className="running-header-tools">
          {sourceState ? (
            <span className="source-state" data-state={sourceState.state}>
              {sourceState.label}
            </span>
          ) : null}
          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
