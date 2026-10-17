"use client";

import { useEffect, useState } from "react";

import { API_URL, fetchHealth } from "@/lib/api";
import type { Health } from "@/lib/types";

export function SiteFooter() {
  const [health, setHealth] = useState<Health | null | "offline">(null);

  useEffect(() => {
    const controller = new AbortController();
    fetchHealth(controller.signal)
      .then(setHealth)
      .catch((error) => {
        if (error?.name !== "AbortError") setHealth("offline");
      });
    return () => controller.abort();
  }, []);

  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div>
          <p>
            Knockout is a research and drug-safety tool. Nothing on this page is medical advice; every prediction is a
            hypothesis built from public records.
          </p>
          <p>
            Sources: ChEMBL, the IUIS classification through the Helix catalog, Orphanet, the Human Phenotype Ontology,
            and openFDA labels and adverse-event reports. Built at LA Hacks 2026.
          </p>
        </div>
        <div className="health" aria-live="polite">
          {health === null ? <span>Checking the API</span> : null}
          {health === "offline" ? <span data-ok="false">API not reachable at {API_URL}</span> : null}
          {health && health !== "offline" ? (
            <>
              <span>API {health.status}</span>
              <span data-ok={health.gemini_key}>Gemini key {health.gemini_key ? "set" : "missing"}</span>
              <span data-ok={health.openfda_key}>openFDA key {health.openfda_key ? "set" : "missing"}</span>
              <span>Store: {health.store}</span>
            </>
          ) : null}
        </div>
      </div>
    </footer>
  );
}
