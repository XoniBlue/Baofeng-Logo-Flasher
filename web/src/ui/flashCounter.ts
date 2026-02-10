const COUNTER_BASE_URL = "https://logo-flasher-counter.robbiem707-354.workers.dev";

const completedSessions = new Set<string>();
const inFlightSessions = new Set<string>();

interface CountResponse {
  total: number;
}

interface IncrementResponse extends CountResponse {
  deduped?: boolean;
}

export async function fetchGlobalFlashCount(): Promise<number> {
  const response = await fetch(`${COUNTER_BASE_URL}/count`, {
    method: "GET"
  });
  if (!response.ok) {
    throw new Error(`Counter fetch failed with status ${response.status}`);
  }
  const body = (await response.json()) as CountResponse;
  if (typeof body.total !== "number" || !Number.isFinite(body.total)) {
    throw new Error("Counter fetch returned invalid payload");
  }
  return body.total;
}

export async function recordSuccessfulFlashOnce(sessionId: string): Promise<number | null> {
  if (!sessionId || completedSessions.has(sessionId) || inFlightSessions.has(sessionId)) {
    return null;
  }

  inFlightSessions.add(sessionId);
  try {
    const response = await fetch(`${COUNTER_BASE_URL}/increment`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: JSON.stringify({ sessionId })
    });
    if (!response.ok) {
      throw new Error(`Counter increment failed with status ${response.status}`);
    }
    const body = (await response.json()) as IncrementResponse;
    if (typeof body.total !== "number" || !Number.isFinite(body.total)) {
      throw new Error("Counter increment returned invalid payload");
    }
    completedSessions.add(sessionId);
    return body.total;
  } catch (error) {
    console.error("Flash counter increment failed:", error);
    return null;
  } finally {
    inFlightSessions.delete(sessionId);
  }
}
