import { formatCount, formatRatio } from "@/lib/format";
import type { TrendQuarter } from "@/lib/types";

const WIDTH = 240;
const HEIGHT = 64;

export function TrendChart({
  term,
  quarters,
  alertQuarters = [],
  manual = false,
}: {
  term: string;
  quarters: TrendQuarter[];
  alertQuarters?: string[];
  manual?: boolean;
}) {
  const ordered = [...quarters].sort((left, right) => left.quarter.localeCompare(right.quarter));
  const highest = Math.max(0, ...ordered.map((quarter) => quarter.reports));
  const peak = Math.max(1, highest);
  const slot = WIDTH / Math.max(ordered.length, 1);
  const barWidth = Math.max(2, Math.min(18, slot - 3));
  const total = ordered.reduce((sum, quarter) => sum + quarter.reports, 0);
  const alerted = new Set(alertQuarters);
  const latest = ordered[ordered.length - 1];
  const latestPrr = latest?.prr_infinite ? "∞" : latest?.prr != null ? formatRatio(latest.prr) : null;

  return (
    <figure className="trend">
      <figcaption>
        <span className="mono">{term}</span>
        <span>
          {highest
            ? `reports received each quarter, peak ${formatCount(highest)}`
            : "no reports in these quarters"}
          {latestPrr ? ` · PRR ${latestPrr}, all reports to ${latest.quarter}` : ""}
        </span>
        {manual ? (
          <span className="trend-manual">
            Term supplied to the watch agent by hand, not from this report&apos;s mapping
          </span>
        ) : null}
      </figcaption>
      {ordered.length ? (
        <>
          <svg
            viewBox={`0 0 ${WIDTH} ${HEIGHT}`}
            preserveAspectRatio="none"
            role="img"
            aria-label={`${term}: ${formatCount(total)} reports over ${ordered.length} quarters, from ${ordered[0].quarter} to ${ordered[ordered.length - 1].quarter}`}
          >
            {ordered.map((quarter, index) => {
              const height = Math.max(quarter.reports ? 1.5 : 0, (quarter.reports / peak) * (HEIGHT - 2));
              return (
                <rect
                  key={quarter.quarter}
                  className="trend-bar"
                  data-alert={alerted.has(quarter.quarter)}
                  x={index * slot + (slot - barWidth) / 2}
                  y={HEIGHT - height}
                  width={barWidth}
                  height={height}
                  rx={1}
                >
                  <title>
                    {quarter.quarter}: {formatCount(quarter.reports)} reports
                    {alerted.has(quarter.quarter) ? ", crossed the signal threshold" : ""}
                  </title>
                </rect>
              );
            })}
            <line className="trend-baseline" x1={0} x2={WIDTH} y1={HEIGHT - 0.5} y2={HEIGHT - 0.5} />
          </svg>
          <div className="trend-axis">
            <span>{ordered[0].quarter}</span>
            <span>{ordered[ordered.length - 1].quarter}</span>
          </div>
        </>
      ) : (
        <p className="evidence-note">No quarters recorded.</p>
      )}
    </figure>
  );
}
