"""HTTP routes for event-collector."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Iterator
from datetime import UTC, datetime
from queue import Full, Queue
from threading import Lock
from typing import Any, cast

from fastapi import APIRouter, HTTPException, Request, status
from fastapi.responses import HTMLResponse, StreamingResponse

from event_collector.api.schemas import (
    BatchIngestRequest,
    BatchIngestResponse,
    EventEnvelope,
    EventIngestResponse,
    EventRecordResponse,
)
from event_collector.errors import HashConflictError, HashValidationError, StorageError
from event_collector.ingest.service import IngestService
from event_collector.models import EventRecord, IngestResult

router = APIRouter()
debug_router = APIRouter()
HTTP_UNPROCESSABLE_ENTITY = 422
DEBUG_STREAM_MEDIA_TYPE = "application/x-ndjson"
DEBUG_PAGE_HTML = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>event-collector debug</title>
  <link rel="icon" href="data:,">
  <style>
    :root {
      color-scheme: dark;
      --bg: #111827;
      --panel: #1f2937;
      --line: #374151;
      --text: #f9fafb;
      --muted: #9ca3af;
      --accent: #38bdf8;
      --ok: #34d399;
      --warn: #fbbf24;
      --danger: #fb7185;
    }

    * {
      box-sizing: border-box;
    }

    body {
      margin: 0;
      min-height: 100vh;
      background: var(--bg);
      color: var(--text);
      font-size: 12px;
      font-family:
        ui-sans-serif,
        system-ui,
        -apple-system,
        BlinkMacSystemFont,
        "Segoe UI",
        sans-serif;
      letter-spacing: 0;
      line-height: 1.25;
    }

    main {
      width: calc(100vw - 12px);
      margin: 0 auto;
      padding: 6px 0;
    }

    header,
    .toolbar,
    .filters,
    .empty,
    .event,
    .copy-fallback {
      border: 1px solid var(--line);
      background: var(--panel);
      border-radius: 5px;
    }

    header {
      display: flex;
      align-items: baseline;
      justify-content: space-between;
      gap: 10px;
      padding: 6px 8px;
    }

    h1 {
      margin: 0;
      font-size: 15px;
      font-weight: 700;
      white-space: nowrap;
    }

    .meta {
      display: flex;
      flex-wrap: wrap;
      justify-content: flex-end;
      gap: 4px 12px;
      color: var(--muted);
      font-size: 11px;
    }

    .toolbar {
      display: grid;
      grid-template-columns: 1fr auto auto auto;
      align-items: center;
      gap: 8px;
      margin: 6px 0;
      padding: 4px 6px;
    }

    .status {
      display: inline-flex;
      align-items: center;
      gap: 5px;
      font-size: 11px;
      color: var(--muted);
    }

    #refresh {
      justify-self: center;
    }

    #toggleEvents {
      justify-self: center;
    }

    #clear {
      justify-self: end;
    }

    .filters {
      display: grid;
      grid-template-columns:
        minmax(180px, 1fr)
        minmax(180px, 1fr)
        minmax(180px, 1fr)
        auto
        auto;
      gap: 6px;
      align-items: end;
      margin: 0 0 6px;
      padding: 5px 6px;
    }

    label {
      display: grid;
      gap: 2px;
      color: var(--muted);
      font-size: 10.5px;
    }

    input {
      width: 100%;
      min-width: 0;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: #0f172a;
      color: var(--text);
      padding: 3px 5px;
      font: inherit;
      font-size: 11px;
    }

    input:focus {
      border-color: var(--accent);
      outline: 0;
    }

    .dot {
      width: 7px;
      height: 7px;
      border-radius: 50%;
      background: var(--warn);
    }

    .dot.connected {
      background: var(--ok);
    }

    .dot.disconnected {
      background: var(--danger);
    }

    button {
      border: 1px solid var(--line);
      border-radius: 4px;
      background: #0f172a;
      color: var(--text);
      padding: 3px 7px;
      font: inherit;
      font-size: 11px;
      cursor: pointer;
    }

    button:hover {
      border-color: var(--accent);
    }

    .events {
      display: grid;
      gap: 4px;
    }

    .empty {
      padding: 10px;
      color: var(--muted);
      text-align: center;
    }

    .copy-fallback {
      display: grid;
      gap: 4px;
      margin: 0 0 6px;
      padding: 5px 6px;
    }

    .copy-fallback[hidden] {
      display: none;
    }

    .json-window {
      position: relative;
      background: #020617;
    }

    .event-copy {
      position: absolute;
      top: 5px;
      right: 7px;
      z-index: 1;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      width: 24px;
      height: 22px;
      padding: 0;
      color: var(--muted);
    }

    .event-copy svg {
      width: 14px;
      height: 14px;
      fill: none;
      stroke: currentColor;
      stroke-width: 1.8;
      stroke-linecap: round;
      stroke-linejoin: round;
    }

    .event-copy.copied {
      color: var(--ok);
    }

    textarea {
      width: 100%;
      min-height: 140px;
      border: 1px solid var(--line);
      border-radius: 4px;
      background: #020617;
      color: #d1fae5;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 10.5px;
      line-height: 1.3;
      resize: vertical;
    }

    .event {
      overflow: hidden;
    }

    .event summary {
      display: grid;
      grid-template-columns:
        minmax(180px, 1.2fr)
        minmax(90px, 0.45fr)
        minmax(145px, 0.65fr)
        minmax(230px, 1fr);
      gap: 8px;
      padding: 4px 7px;
      cursor: pointer;
      list-style: none;
      border-bottom: 1px solid var(--line);
    }

    .event:not([open]) summary {
      border-bottom: 0;
    }

    .event summary::-webkit-details-marker {
      display: none;
    }

    .event-name {
      color: var(--text);
      font-weight: 700;
      font-size: 12px;
      overflow-wrap: anywhere;
    }

    .event-id,
    .event-time,
    .event-source {
      color: var(--muted);
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 10.5px;
      overflow-wrap: anywhere;
    }

    pre {
      margin: 0;
      padding: 7px;
      padding-right: 38px;
      overflow: auto;
      max-height: 320px;
      background: #020617;
      color: #d1fae5;
      font-family: ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;
      font-size: 10.5px;
      line-height: 1.3;
      white-space: pre-wrap;
      overflow-wrap: anywhere;
    }

    @media (max-width: 760px) {
      main {
        width: calc(100vw - 8px);
        padding: 4px 0;
      }

      header,
      .toolbar,
      .filters {
        align-items: stretch;
      }

      header {
        display: grid;
        gap: 4px;
      }

      .meta {
        justify-content: flex-start;
      }

      .event summary {
        grid-template-columns: minmax(140px, 1fr) minmax(120px, 1fr);
      }

      .filters {
        grid-template-columns: 1fr 1fr;
      }

      button {
        width: 100%;
      }
    }
  </style>
</head>
<body>
  <main>
    <header>
      <h1>event-collector debug</h1>
      <div class="meta">
        <span>stream: /debug/stream</span>
        <span>format: newline-delimited JSON</span>
        <span id="count">events: 0</span>
      </div>
    </header>

    <section class="toolbar" aria-label="debug controls">
      <div class="status">
        <span id="dot" class="dot"></span>
        <span id="status">connecting</span>
      </div>
      <button id="refresh" type="button">Refresh</button>
      <button
        id="toggleEvents"
        type="button"
        aria-label="Open all events"
        title="Open all events"
      >
        Open
      </button>
      <button id="clear" type="button">Clear</button>
    </section>

    <section class="filters" aria-label="debug filters">
      <label>
        correlation_id
        <input id="correlation" list="correlations" autocomplete="off">
      </label>
      <datalist id="correlations"></datalist>
      <label>
        from
        <input id="from" type="datetime-local" step="1">
      </label>
      <label>
        to
        <input id="to" type="datetime-local" step="1">
      </label>
      <button id="copy" type="button">Copy JSON</button>
      <button id="reset" type="button">Reset</button>
    </section>

    <section id="copyFallback" class="copy-fallback" hidden>
      <label for="copyOutput">Clipboard unavailable. Select and copy manually.</label>
      <textarea id="copyOutput" readonly></textarea>
    </section>

    <section id="events" class="events" aria-live="polite">
      <div id="empty" class="empty">Waiting for submitted events.</div>
    </section>
  </main>

  <script>
    const events = document.querySelector("#events");
    const empty = document.querySelector("#empty");
    const count = document.querySelector("#count");
    const statusText = document.querySelector("#status");
    const dot = document.querySelector("#dot");
    const refresh = document.querySelector("#refresh");
    const toggleEvents = document.querySelector("#toggleEvents");
    const clear = document.querySelector("#clear");
    const correlation = document.querySelector("#correlation");
    const correlations = document.querySelector("#correlations");
    const from = document.querySelector("#from");
    const to = document.querySelector("#to");
    const copy = document.querySelector("#copy");
    const reset = document.querySelector("#reset");
    const copyFallback = document.querySelector("#copyFallback");
    const copyOutput = document.querySelector("#copyOutput");
    const messages = [];
    let total = 0;
    let eventsDefaultOpen = false;
    let fromFollowsNow = true;
    let toFollowsNow = true;

    function localInputValue(date) {
      const offsetMs = date.getTimezoneOffset() * 60000;
      return new Date(date.getTime() - offsetMs).toISOString().slice(0, 19);
    }

    function resetWindow() {
      const now = new Date();
      from.value = localInputValue(new Date(now.getTime() - 15 * 60 * 1000));
      to.value = localInputValue(now);
      fromFollowsNow = true;
      toFollowsNow = true;
    }

    resetWindow();

    clear.addEventListener("click", () => {
      messages.length = 0;
      render();
    });

    refresh.addEventListener("click", async () => {
      refresh.disabled = true;
      refresh.textContent = "Refreshing";
      try {
        await refreshHistory();
        refresh.textContent = "Refreshed";
      } catch (error) {
        refresh.textContent = "Refresh failed";
      } finally {
        setTimeout(() => {
          refresh.disabled = false;
          refresh.textContent = "Refresh";
        }, 900);
      }
    });

    toggleEvents.addEventListener("click", () => {
      setEventsOpen(!eventsDefaultOpen);
    });

    reset.addEventListener("click", () => {
      correlation.value = "";
      resetWindow();
      render();
    });

    correlation.addEventListener("input", render);
    from.addEventListener("input", () => {
      fromFollowsNow = false;
      render();
    });
    to.addEventListener("input", () => {
      toFollowsNow = false;
      render();
    });

    copy.addEventListener("click", async () => {
      const eventJson = JSON.stringify(filteredMessages().map((message) => message.event), null, 2);
      try {
        await navigator.clipboard.writeText(eventJson);
        copy.textContent = "Copied";
        copyFallback.hidden = true;
        setTimeout(() => {
          copy.textContent = "Copy JSON";
        }, 1200);
      } catch {
        copyOutput.value = eventJson;
        copyFallback.hidden = false;
        copyOutput.focus();
        copyOutput.select();
      }
    });

    async function copyText(text, button) {
      try {
        await navigator.clipboard.writeText(text);
        button.classList.add("copied");
        button.setAttribute("aria-label", "Copied event JSON");
        button.setAttribute("title", "Copied");
        setTimeout(() => {
          button.classList.remove("copied");
          button.setAttribute("aria-label", "Copy event JSON");
          button.setAttribute("title", "Copy event JSON");
        }, 1200);
      } catch {
        copyOutput.value = text;
        copyFallback.hidden = false;
        copyOutput.focus();
        copyOutput.select();
      }
    }

    function setStatus(value, state) {
      statusText.textContent = value;
      dot.className = `dot ${state}`;
    }

    function setEventsOpen(open) {
      eventsDefaultOpen = open;
      [...events.querySelectorAll(".event")].forEach((node) => {
        node.open = open;
      });
      const label = open ? "Collapse" : "Open";
      const description = open ? "Collapse all events" : "Open all events";
      toggleEvents.textContent = label;
      toggleEvents.setAttribute("aria-label", description);
      toggleEvents.setAttribute("title", description);
    }

    function messageTime(message) {
      const value = Date.parse(message.streamed_at || "");
      return Number.isNaN(value) ? null : value;
    }

    function inputTime(input) {
      return input.value ? new Date(input.value).getTime() : null;
    }

    function messageCorrelation(message) {
      return message.event?.correlation_id || "";
    }

    function filteredMessages() {
      const correlationValue = correlation.value.trim();
      const fromTime = inputTime(from);
      const toTime = inputTime(to);
      return messages.filter((message) => {
        const time = messageTime(message);
        if (correlationValue && messageCorrelation(message) !== correlationValue) {
          return false;
        }
        if (fromTime !== null && (time === null || time < fromTime)) {
          return false;
        }
        if (toTime !== null && (time === null || time > toTime)) {
          return false;
        }
        return true;
      });
    }

    function updateCorrelationOptions() {
      const values = [...new Set(messages.map(messageCorrelation).filter(Boolean))].sort();
      correlations.replaceChildren(...values.map((value) => {
        const option = document.createElement("option");
        option.value = value;
        return option;
      }));
    }

    function mergeMessages(incoming) {
      const seen = new Set(messages.map((message) => message.event_id));
      for (const message of incoming) {
        if (!message.event_id || seen.has(message.event_id)) {
          continue;
        }
        messages.push(message);
        seen.add(message.event_id);
      }
      while (messages.length > 1000) {
        messages.shift();
      }
    }

    function render() {
      updateCorrelationOptions();
      const visible = filteredMessages();
      total = visible.length;
      count.textContent = `events: ${total} / ${messages.length}`;
      [...events.querySelectorAll(".event")].forEach((node) => node.remove());
      empty.hidden = visible.length > 0;
      for (const message of visible) {
        appendEvent(message);
      }
    }

    async function refreshHistory() {
      const response = await fetch("/debug/history", {
        headers: { "Accept": "application/json" },
        cache: "no-store",
      });
      if (!response.ok) {
        throw new Error(`history failed: ${response.status}`);
      }
      mergeMessages(await response.json());
      if (fromFollowsNow) {
        from.value = localInputValue(new Date(Date.now() - 15 * 60 * 1000));
      }
      if (toFollowsNow) {
        to.value = localInputValue(new Date());
      }
      render();
    }

    function appendEvent(message) {
      const details = document.createElement("details");
      details.className = "event";
      details.open = eventsDefaultOpen;

      const source = message.source || {};
      const batch = Number.isInteger(source.batch_index) ? ` #${source.batch_index}` : "";
      const summary = document.createElement("summary");
      summary.innerHTML = `
        <span class="event-name"></span>
        <span class="event-source"></span>
        <span class="event-time"></span>
        <span class="event-id"></span>
      `;
      const endpointLabel = source.endpoint || "unknown";
      summary.querySelector(".event-name").textContent = message.event_name || "unknown event";
      summary.querySelector(".event-source").textContent = `${endpointLabel}${batch}`;
      summary.querySelector(".event-time").textContent = message.streamed_at || "";
      summary.querySelector(".event-id").textContent = message.event_id || "";

      const eventJson = JSON.stringify(message, null, 2);
      const jsonWindow = document.createElement("div");
      jsonWindow.className = "json-window";

      const eventCopy = document.createElement("button");
      eventCopy.className = "event-copy";
      eventCopy.type = "button";
      eventCopy.setAttribute("aria-label", "Copy event JSON");
      eventCopy.setAttribute("title", "Copy event JSON");
      eventCopy.innerHTML = `
        <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">
          <rect x="9" y="9" width="11" height="11" rx="2"></rect>
          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"></path>
        </svg>
      `;
      eventCopy.addEventListener("click", () => copyText(eventJson, eventCopy));

      const pre = document.createElement("pre");
      pre.textContent = eventJson;
      jsonWindow.append(eventCopy, pre);

      details.append(summary, jsonWindow);
      events.prepend(details);

      while (events.querySelectorAll(".event").length > 200) {
        events.querySelector(".event:last-of-type").remove();
      }
    }

    async function connect() {
      setStatus("connecting", "");
      const response = await fetch("/debug/stream", {
        headers: { "Accept": "application/x-ndjson" },
        cache: "no-store",
      });
      if (!response.ok || !response.body) {
        throw new Error(`stream failed: ${response.status}`);
      }

      setStatus("connected", "connected");
      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) {
          break;
        }
        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split("\\n");
        buffer = lines.pop();
        for (const line of lines) {
          if (!line.trim()) {
            continue;
          }
          mergeMessages([JSON.parse(line)]);
          if (fromFollowsNow) {
            from.value = localInputValue(new Date(Date.now() - 15 * 60 * 1000));
          }
          if (toFollowsNow) {
            to.value = localInputValue(new Date());
          }
          render();
        }
      }
    }

    async function run() {
      while (true) {
        try {
          await connect();
        } catch (error) {
          setStatus(`disconnected: ${error.message}`, "disconnected");
          await new Promise((resolve) => setTimeout(resolve, 1500));
        }
      }
    }

    run();
  </script>
</body>
</html>
"""


class NDJSONStreamingResponse(StreamingResponse):
    media_type = DEBUG_STREAM_MEDIA_TYPE


def _service(request: Request) -> IngestService:
    return cast(IngestService, request.app.state.ingest_service)


class DebugEventBus:
    """Fan out submitted events to connected debug stream clients."""

    def __init__(self, *, queue_size: int = 1000, history_size: int = 1000) -> None:
        self._queue_size = queue_size
        self._subscribers: set[Queue[str]] = set()
        self._history: deque[str] = deque(maxlen=history_size)
        self._lock = Lock()

    def subscribe(self) -> Queue[str]:
        subscriber: Queue[str] = Queue(maxsize=self._queue_size)
        with self._lock:
            for line in self._history:
                try:
                    subscriber.put_nowait(line)
                except Full:
                    break
            self._subscribers.add(subscriber)
        return subscriber

    def unsubscribe(self, subscriber: Queue[str]) -> None:
        with self._lock:
            self._subscribers.discard(subscriber)

    def publish(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with self._lock:
            self._history.append(line)
            subscribers = tuple(self._subscribers)

        for subscriber in subscribers:
            try:
                subscriber.put_nowait(line)
            except Full:
                continue

    def history(self) -> list[dict[str, Any]]:
        with self._lock:
            lines = tuple(self._history)
        return [json.loads(line) for line in lines]


def _debug_event_bus(request: Request) -> DebugEventBus | None:
    return cast(DebugEventBus | None, getattr(request.app.state, "debug_event_bus", None))


def _required_debug_event_bus(request: Request) -> DebugEventBus:
    bus = _debug_event_bus(request)
    if bus is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="debug stream disabled")
    return bus


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/readyz")
def readyz(request: Request) -> dict[str, str]:
    service = _service(request)
    if not service.ledger.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="ledger not ready",
        )
    if not service.storage.is_ready():
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="storage not ready",
        )
    return {"status": "ready"}


@router.post("/v1/events", response_model=EventIngestResponse)
def ingest_event(envelope: EventEnvelope, request: Request) -> EventIngestResponse:
    _publish_debug_event(request, envelope, endpoint="/v1/events", batch_index=None)
    try:
        result = _service(request).ingest(envelope)
    except HashConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except HashValidationError as exc:
        raise HTTPException(
            status_code=HTTP_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except StorageError as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc
    return _response_from_result(result)


@router.post("/v1/events:batch", response_model=BatchIngestResponse)
def ingest_event_batch(
    batch: BatchIngestRequest,
    request: Request,
) -> BatchIngestResponse:
    results: list[EventIngestResponse] = []
    service = _service(request)
    for index, envelope in enumerate(batch.events):
        _publish_debug_event(request, envelope, endpoint="/v1/events:batch", batch_index=index)
        try:
            results.append(_response_from_result(service.ingest(envelope)))
        except HashConflictError as exc:
            results.append(
                EventIngestResponse(
                    event_id=envelope.normalized_event_id(),
                    status="hash_conflict",
                    storage_uri=None,
                    received_at=envelope.observed_at or envelope.occurred_at,
                    stored_at=None,
                    message=str(exc),
                )
            )
        except (HashValidationError, StorageError) as exc:
            results.append(
                EventIngestResponse(
                    event_id=envelope.normalized_event_id(),
                    status="failed",
                    storage_uri=None,
                    received_at=envelope.observed_at or envelope.occurred_at,
                    stored_at=None,
                    message=str(exc),
                )
            )
    return BatchIngestResponse(results=results)


@router.get("/v1/events/{event_id}", response_model=EventRecordResponse)
def get_event(event_id: str, request: Request) -> EventRecordResponse:
    record = _service(request).get_event(event_id)
    if record is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="event not found")
    return _record_response(record)


def _response_from_result(result: IngestResult) -> EventIngestResponse:
    return EventIngestResponse(
        event_id=result.event_id,
        status=result.status,
        storage_uri=result.storage_uri,
        received_at=result.received_at,
        stored_at=result.stored_at,
        message=result.message,
    )


def _record_response(record: EventRecord) -> EventRecordResponse:
    return EventRecordResponse(
        event_id=record.event_id,
        event_name=record.event_name,
        event_version=record.event_version,
        producer_service=record.producer_service,
        partition_id=record.partition_id,
        subject_type=record.subject_type,
        subject_id=record.subject_id,
        payload_sha256=record.payload_sha256,
        event_sha256=record.event_sha256,
        status=record.status,
        storage_uri=record.storage_uri,
        received_at=record.received_at,
        stored_at=record.stored_at,
        last_error=record.last_error,
        raw_envelope=json.loads(record.raw_envelope_json),
    )


@debug_router.get("/debug", response_class=HTMLResponse)
def debug_page(request: Request) -> HTMLResponse:
    _required_debug_event_bus(request)
    return HTMLResponse(DEBUG_PAGE_HTML)


@debug_router.get("/debug/history", include_in_schema=False)
def debug_history(request: Request) -> list[dict[str, Any]]:
    return _required_debug_event_bus(request).history()


@debug_router.get("/debug/stream", response_class=NDJSONStreamingResponse, include_in_schema=False)
def debug_stream(request: Request) -> StreamingResponse:
    bus = _required_debug_event_bus(request)

    def event_lines() -> Iterator[str]:
        subscriber = bus.subscribe()
        try:
            while True:
                yield subscriber.get()
        finally:
            bus.unsubscribe(subscriber)

    return NDJSONStreamingResponse(event_lines())


def _publish_debug_event(
    request: Request,
    envelope: EventEnvelope,
    *,
    endpoint: str,
    batch_index: int | None,
) -> None:
    bus = _debug_event_bus(request)
    if bus is None:
        return

    source: dict[str, Any] = {"endpoint": endpoint}
    if batch_index is not None:
        source["batch_index"] = batch_index

    bus.publish(
        {
            "debug_version": "1.0",
            "streamed_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
            "source": source,
            "event_id": envelope.normalized_event_id(),
            "event_name": envelope.event_name,
            "producer_service": envelope.producer_service,
            "event": envelope.canonical_event(),
        }
    )
