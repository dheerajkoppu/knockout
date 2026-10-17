import Link from "next/link";

import { RunningHeader } from "@/components/RunningHeader";

export default function NotFound() {
  return (
    <>
      <RunningHeader />
      <main>
        <div className="page">
          <div className="notice">
            <h2>No page here</h2>
            <p>
              Reports live at <code>/drug/&lt;generic name&gt;</code>. <Link href="/">Search for a drug</Link>.
            </p>
          </div>
        </div>
      </main>
    </>
  );
}
