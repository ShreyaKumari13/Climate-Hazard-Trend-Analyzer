import { useCallback, useState } from "react";
import { analyze } from "../api/client.js";

export function useAnalysis() {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const run = useCallback(async (params) => {
    setLoading(true);
    setError(null);
    try {
      const result = await analyze(params);
      setData(result);
    } catch (e) {
      setError(e.message || "Something went wrong.");
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  return { data, loading, error, run };
}
