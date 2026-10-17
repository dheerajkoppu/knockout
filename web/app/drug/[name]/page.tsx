import type { Metadata } from "next";

import { ReportView } from "@/components/ReportView";
import { titleCase } from "@/lib/format";

type Parameters = { params: Promise<{ name: string }>; searchParams: Promise<{ fixture?: string }> };

export async function generateMetadata({ params }: Parameters): Promise<Metadata> {
  const { name } = await params;
  return { title: titleCase(decodeURIComponent(name)) };
}

export default async function DrugPage({ params, searchParams }: Parameters) {
  const { name } = await params;
  const { fixture } = await searchParams;
  return <ReportView name={decodeURIComponent(name).trim().toLowerCase()} fixtureRequested={fixture === "1" || fixture === "true"} />;
}
