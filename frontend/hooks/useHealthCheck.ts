"use client";

import { useEffect, useState } from "react";
import { checkHealth } from "@/api/legal";

export function useHealthCheck() {
  const [status, setStatus] = useState<"checking" | "ok" | "error">("checking");

  useEffect(() => {
    checkHealth()
      .then(() => setStatus("ok"))
      .catch(() => setStatus("error"));
  }, []);

  return status;
}
