import { VERDICTS } from "@/lib/format";
import type { Verdict } from "@/lib/types";

export function VerdictMark({ verdict }: { verdict: Verdict }) {
  return (
    <svg className="verdict-mark" data-verdict={verdict} viewBox="0 0 12 12" aria-hidden="true">
      {verdict === "on_label" ? <rect x="1" y="1" width="10" height="10" rx="1" fill="currentColor" /> : null}
      {verdict === "signal_in_reports" ? (
        <>
          <rect x="1.5" y="1.5" width="9" height="9" rx="0.75" fill="none" stroke="currentColor" strokeWidth="1.25" />
          <path d="M1.5 10.5 10.5 1.5V10.5Z" fill="currentColor" />
        </>
      ) : null}
      {verdict === "no_signal" ? (
        <rect x="1.5" y="1.5" width="9" height="9" rx="0.75" fill="none" stroke="currentColor" strokeWidth="1.25" />
      ) : null}
      {verdict === "unknown" ? (
        <rect
          x="1.5"
          y="1.5"
          width="9"
          height="9"
          rx="0.75"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.25"
          strokeDasharray="2 1.6"
        />
      ) : null}
    </svg>
  );
}

export function VerdictTag({ verdict }: { verdict: Verdict }) {
  return (
    <span className="verdict-tag" data-verdict={verdict} title={VERDICTS[verdict].meaning}>
      <VerdictMark verdict={verdict} />
      {VERDICTS[verdict].label}
    </span>
  );
}
