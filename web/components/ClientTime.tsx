"use client";

import { useEffect, useState } from "react";

import { formatDateTime, relativeTime } from "@/lib/format";

// Times render after mount, in the reader's own time zone, so server and browser never disagree.
export function ClientTime({ value, relative = false }: { value: string | null | undefined; relative?: boolean }) {
  const [text, setText] = useState("");
  useEffect(() => {
    if (!value) return;
    const ago = relativeTime(value);
    setText(relative && ago ? `${formatDateTime(value)}, ${ago}` : formatDateTime(value));
  }, [value, relative]);
  return <time dateTime={value ?? undefined}>{text || " "}</time>;
}
