/**
 * Tiny SSE consumer for `/api/ask`. Reads the Fetch streams API directly
 * instead of pulling in an EventSource shim, because we need POST (the
 * native `EventSource` is GET-only) and the parsing we need is simple.
 *
 * Emits one parsed SseMessage per `event:`+`data:` pair, in order.
 */

export interface SseMessage {
  event: string;
  data: string;
}

export async function* readSse(
  response: Response,
  signal?: AbortSignal,
): AsyncGenerator<SseMessage, void, void> {
  if (!response.body) throw new Error("Response has no body");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const onAbort = () => reader.cancel().catch(() => {});
  signal?.addEventListener("abort", onAbort, { once: true });

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) {
        if (buffer.trim()) {
          const msg = parseEvent(buffer);
          if (msg) yield msg;
        }
        return;
      }
      buffer += decoder.decode(value, { stream: true });

      // Events are separated by blank lines (\n\n).
      let idx: number;
      while ((idx = buffer.indexOf("\n\n")) !== -1) {
        const raw = buffer.slice(0, idx);
        buffer = buffer.slice(idx + 2);
        const msg = parseEvent(raw);
        if (msg) yield msg;
      }
    }
  } finally {
    signal?.removeEventListener("abort", onAbort);
  }
}

function parseEvent(raw: string): SseMessage | null {
  let event = "message";
  const dataLines: string[] = [];
  for (const line of raw.split("\n")) {
    if (!line || line.startsWith(":")) continue;
    if (line.startsWith("event:")) {
      event = line.slice(6).trim();
    } else if (line.startsWith("data:")) {
      dataLines.push(line.slice(5).trimStart());
    }
  }
  if (!dataLines.length) return null;
  return { event, data: dataLines.join("\n") };
}

// Parsed per-event payload shapes mirroring what the backend emits.
export interface TokenEvent {
  type: "token";
  text: string;
}
export interface ToolUseEvent {
  type: "tool_use";
  id: string;
  tool: string;
  input: Record<string, unknown>;
}
export interface ToolResultEvent {
  type: "tool_result";
  id: string;
  output: unknown;
  is_error: boolean;
}
export interface DoneEvent {
  type: "done";
  turns_used: number;
  stop_reason: string;
}
export interface ErrorEvent {
  type: "error";
  message: string;
}
export type AskEvent =
  | TokenEvent
  | ToolUseEvent
  | ToolResultEvent
  | DoneEvent
  | ErrorEvent;

export function parseAskEvent(msg: SseMessage): AskEvent | null {
  try {
    switch (msg.event) {
      case "token":
        // token data is a JSON-encoded string fragment.
        return { type: "token", text: JSON.parse(msg.data) };
      case "tool_use":
        return { type: "tool_use", ...JSON.parse(msg.data) };
      case "tool_result":
        return { type: "tool_result", ...JSON.parse(msg.data) };
      case "done":
        return { type: "done", ...JSON.parse(msg.data) };
      case "error":
        return { type: "error", ...JSON.parse(msg.data) };
      default:
        return null;
    }
  } catch {
    return null;
  }
}
