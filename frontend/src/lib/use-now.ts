"use client";

import { useEffect, useState } from "react";

/** Wall clock in epoch seconds, ticking only while something is running. */
export function useNow(running: boolean): number {
  const [now, setNow] = useState(0);
  useEffect(() => {
    if (!running) return;
    const id = setInterval(() => setNow(Date.now() / 1000), 200);
    return () => clearInterval(id);
  }, [running]);
  return now;
}
