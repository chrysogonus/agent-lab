"use client";

import { useCallback, useEffect, useState } from "react";
import { listApprovals, type OpenApproval } from "./api";

const POLL_MS = 2000;

/** Every open approval request, from any page (FR-018). */
export function useApprovals(): { open: OpenApproval[]; refresh: () => void } {
  const [open, setOpen] = useState<OpenApproval[]>([]);
  const refresh = useCallback(() => {
    listApprovals().then(setOpen, () => setOpen([])); // no backend, no requests
  }, []);
  useEffect(() => {
    refresh();
    const timer = window.setInterval(refresh, POLL_MS);
    return () => window.clearInterval(timer);
  }, [refresh]);
  return { open, refresh };
}
