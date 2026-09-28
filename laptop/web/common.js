// Shared helpers for the dashboard and phone pages.

export const MODES = [
  ["manual", "Manual"],
  ["follow", "Follow"],
  ["explore", "Explore"],
  ["replay", "Replay"],
  ["handheld", "Hand-held"],
];

// Auto-reconnecting WebSocket. JSON "state"/"error" messages and binary frames.
export function connectSocket(path, { onState, onFrame, onError, onStatus } = {}) {
  let ws = null;
  let retry = 0;
  const open = () => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    ws = new WebSocket(`${proto}://${location.host}${path}`);
    ws.binaryType = "blob";
    ws.onopen = () => {
      retry = 0;
      onStatus?.(true);
    };
    ws.onclose = () => {
      onStatus?.(false);
      setTimeout(open, Math.min(2000, 250 * 2 ** retry++));
    };
    ws.onmessage = (event) => {
      if (typeof event.data !== "string") {
        onFrame?.(event.data);
        return;
      }
      let msg;
      try {
        msg = JSON.parse(event.data);
      } catch {
        return;
      }
      if (msg.type === "state") onState?.(msg);
      else if (msg.type === "error") onError?.(msg.message);
    };
  };
  open();
  return {
    send(obj) {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(obj));
    },
    sendBinary(data) {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send(data);
    },
    get buffered() {
      return ws && ws.readyState === WebSocket.OPEN ? ws.bufferedAmount : Infinity;
    },
  };
}

// Where a source of srcW x srcH lands inside a box of boxW x boxH with object-fit: contain.
export function containRect(boxW, boxH, srcW, srcH) {
  if (!srcW || !srcH) return { x: 0, y: 0, w: boxW, h: boxH };
  const scale = Math.min(boxW / srcW, boxH / srcH);
  const w = srcW * scale;
  const h = srcH * scale;
  return { x: (boxW - w) / 2, y: (boxH - h) / 2, w, h };
}

// Pointer position -> normalised 0..1 image coords (null if outside the image).
export function toImageCoords(event, element, srcW, srcH) {
  const box = element.getBoundingClientRect();
  const r = containRect(box.width, box.height, srcW, srcH);
  const x = (event.clientX - box.left - r.x) / r.w;
  const y = (event.clientY - box.top - r.y) / r.h;
  return x >= 0 && x <= 1 && y >= 0 && y <= 1 ? { x, y } : null;
}

let toastTimer = null;
export function toast(message) {
  let el = document.querySelector(".toast");
  if (!el) {
    el = document.createElement("div");
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3500);
}

export function buildModeButtons(container, onPick) {
  const buttons = new Map();
  for (const [value, label] of MODES) {
    const b = document.createElement("button");
    b.textContent = label;
    b.addEventListener("click", () => onPick(value));
    container.appendChild(b);
    buttons.set(value, b);
  }
  return (active) => buttons.forEach((b, value) => b.classList.toggle("active", value === active));
}

// Keep a <select> of YOLO classes in sync without rebuilding it every update.
export function syncLabels(select, labels) {
  if (select.dataset.count === String(labels.length)) return;
  select.dataset.count = String(labels.length);
  select.replaceChildren(new Option("- tap an object or pick a class -", ""));
  for (const label of labels) select.appendChild(new Option(label, label));
}
