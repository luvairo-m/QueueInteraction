const REQUEST_TIMEOUT_MS = 8_000;
const POLL_INTERVAL_MS = 500;
const POLL_TIMEOUT_MS = 60_000;

class HttpError extends Error {
  constructor(status) {
    super(`Unexpected HTTP status ${status}`);
    this.status = status;
  }
}

async function requestJson(url, options = {}, expectedStatus = 200) {
  const response = await fetch(url, { ...options, signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS) });
  if (response.status !== expectedStatus) throw new HttpError(response.status);
  return response.json();
}

export async function getExample() {
  const { csv } = await requestJson("/demo/example.json");
  return csv;
}

export async function submitJob(csv) {
  const started = performance.now();
  const { id } = await requestJson("/jobs", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ csv }),
  }, 202);
  return { id, elapsed: Math.round(performance.now() - started) };
}

export async function waitForResult(jobUrl) {
  const deadline = performance.now() + POLL_TIMEOUT_MS;
  while (performance.now() < deadline) {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    const job = await requestJson(jobUrl, { cache: "no-store" });
    if (job.status === "DONE") return job.result;
  }
  throw new Error("Polling timed out");
}
