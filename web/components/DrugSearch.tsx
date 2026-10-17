"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

// Drugs from benchmark/drug_set.json whose target has an inborn error of immunity in the catalog.
export const EXAMPLE_DRUGS = ["eculizumab", "pembrolizumab", "nivolumab", "acalabrutinib", "ibrutinib"];

export function DrugSearch() {
  const router = useRouter();
  const [name, setName] = useState("");
  const [pending, setPending] = useState(false);

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const drug = name.trim().toLowerCase();
    if (!drug) return;
    setPending(true);
    router.push(`/drug/${encodeURIComponent(drug)}`);
  }

  return (
    <form className="search" onSubmit={submit} role="search">
      <label className="search-label" htmlFor="drug">
        Drug, by generic name
      </label>
      <div className="search-row">
        <input
          id="drug"
          className="search-input"
          name="drug"
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder="eculizumab"
          autoComplete="off"
          autoCapitalize="none"
          spellCheck={false}
          enterKeyHint="search"
        />
        <button type="submit" className="button button-solid search-submit" disabled={pending}>
          {pending ? "Opening" : "Predict"}
        </button>
      </div>
      <p className="search-examples">
        <span>Try</span>
        {EXAMPLE_DRUGS.map((drug) => (
          <Link key={drug} href={`/drug/${drug}`}>
            {drug}
          </Link>
        ))}
      </p>
      <p className="search-scope">
        It works for drugs that block or activate a protein behind an inborn error of immunity, such as complement
        C5, PD-1, BTK or JAK3. For a drug like aspirin or metformin there is no such disease, so there is nothing to
        predict from.
      </p>
    </form>
  );
}
