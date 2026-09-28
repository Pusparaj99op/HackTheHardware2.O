import { buildModeButtons, connectSocket, syncLabels, toImageCoords, toast } from "/static/common.js";
import { drawMap } from "/static/map.js";

const $ = (id) => document.getElementById(id);
const MANUAL_HZ = 10;
let state = null;
let frame = { w: 640, h: 360 };

const sock = connectSocket("/ws/dash", {
  onState: render,
  onFrame: showFrame,
  onError: toast,
  onStatus: (on) => $("dot-server").classList.toggle("on", on),
});
const setModes = buildModeButtons($("modes"), (mode) => sock.send({ type: "mode", mode }));

// ---------------------------------------------------------------- video
function showFrame(blob) {
  const img = $("video");
  const previous = img.src;
  img.onload = () => {
    frame = { w: img.naturalWidth, h: img.naturalHeight };
    if (previous.startsWith("blob:")) URL.revokeObjectURL(previous);
  };
  img.src = URL.createObjectURL(blob);
  img.hidden = false;
  $("placeholder").hidden = true;
}

$("video").addEventListener("click", (event) => {
  const point = toImageCoords(event, $("video"), frame.w, frame.h);
  if (point) sock.send({ type: "tap", x: point.x, y: point.y });
});

// ---------------------------------------------------------------- render
function describeTarget(t) {
  if (t.point) return `floor point ${t.point.map((v) => v.toFixed(2)).join(", ")}`;
  if (t.label || t.track_id != null) return `${t.label ?? "object"}${t.track_id != null ? ` #${t.track_id}` : ""}`;
  return "none";
}

function renderChips(s) {
  const link = s.link;
  $("dot-phone").classList.toggle("on", s.phone_connected);
  $("dot-car").classList.toggle("on", link.ok);
  $("car-text").textContent = link.ok ? `car ${link.car_ip} ${link.state}` : "car offline";
  $("battery").textContent = link.battery_mv ? `batt ${(link.battery_mv / 1000).toFixed(2)} V` : "batt -";
  $("bumpers").textContent = `bumpers ${link.bumpers.length ? link.bumpers.join("+") : "clear"}`;
  $("bumpers").classList.toggle("bad", link.bumpers.length > 0);
  $("cmd").textContent = `thr ${s.command[0]} / steer ${s.command[1]}`;
  const age = s.vision.age_ms == null ? "" : ` | ${s.vision.age_ms} ms`;
  $("vision").textContent = `vision ${s.vision.status}${age}`;
}

function renderTracks(names) {
  const box = $("tracks");
  const key = names.join("|");
  if (box.dataset.key === key) return;
  box.dataset.key = key;
  box.replaceChildren();
  for (const name of names) {
    const row = document.createElement("div");
    row.className = "row";
    const label = document.createElement("span");
    label.className = "mono";
    label.textContent = name;
    const load = document.createElement("button");
    load.textContent = "Replay";
    load.addEventListener("click", () => sock.send({ type: "track_load", name }));
    row.append(label, load);
    box.appendChild(row);
  }
  if (!names.length) box.textContent = "No saved tracks yet.";
}

function render(s) {
  state = s;
  const kill = $("kill");
  kill.textContent = s.killed ? "ARM (car is killed)" : "KILL  [Space]";
  kill.classList.toggle("armed-off", s.killed);
  $("status").textContent = s.status;
  $("safety").textContent = s.safety ? `SAFETY STOP: ${s.safety}` : "";
  $("notice").textContent = s.notice;
  renderChips(s);
  setModes(s.mode);
  syncLabels($("label"), s.labels);
  if (document.activeElement !== $("label")) $("label").value = s.target.label ?? "";
  $("target").textContent = describeTarget(s.target);
  if (document.activeElement !== $("cap")) {
    $("cap").value = s.speed_cap;
    $("cap-value").textContent = `${Math.round(s.speed_cap)}%`;
  }
  const [x, y, th] = s.pose;
  $("pose").textContent = `x ${x.toFixed(2)} m  y ${y.toFixed(2)} m  heading ${Math.round((th * 180) / Math.PI)} deg`;
  drawMap($("map"), s);
  renderTracks(s.tracks);
}

// ---------------------------------------------------------------- controls
$("kill").addEventListener("click", () => sock.send({ type: state && !state.killed ? "kill" : "arm" }));
$("label").addEventListener("change", (e) => sock.send({ type: "target_class", label: e.target.value || null }));
$("clear-target").addEventListener("click", () => sock.send({ type: "clear_target" }));
$("cap").addEventListener("input", (e) => ($("cap-value").textContent = `${e.target.value}%`));
$("cap").addEventListener("change", (e) => sock.send({ type: "speed_cap", value: Number(e.target.value) }));
$("clear-bumper").addEventListener("click", () => sock.send({ type: "clear_bumper" }));
$("reset").addEventListener("click", () => sock.send({ type: "odom_reset" }));
$("save").addEventListener("click", () => {
  const name = $("track-name").value.trim();
  if (!name) return toast("Type a track name first");
  sock.send({ type: "track_save", name });
});

// ---------------------------------------------------------------- manual driving
const keys = new Set();
let pad = null; // {throttle, steer} while dragging the pad
let wasDriving = false;

function typingInForm() {
  const tag = document.activeElement?.tagName;
  return tag === "INPUT" || tag === "SELECT";
}

window.addEventListener("keydown", (e) => {
  if (e.code === "Space") {
    e.preventDefault();
    sock.send({ type: "kill" }); // Space only ever kills, never arms
    return;
  }
  if (typingInForm()) return;
  const k = e.key.toLowerCase();
  if ("wasd".includes(k) && k.length === 1) keys.add(k);
});
window.addEventListener("keyup", (e) => keys.delete(e.key.toLowerCase()));
window.addEventListener("blur", () => keys.clear());

setInterval(() => {
  let drive = pad;
  if (!drive && keys.size) {
    drive = {
      throttle: keys.has("w") ? 100 : keys.has("s") ? -100 : 0,
      steer: keys.has("a") ? -100 : keys.has("d") ? 100 : 0,
    };
  }
  if (drive) {
    if (state && state.mode !== "manual") sock.send({ type: "mode", mode: "manual" });
    sock.send({ type: "manual", ...drive });
    wasDriving = true;
  } else if (wasDriving) {
    sock.send({ type: "manual", throttle: 0, steer: 0 });
    wasDriving = false;
  }
}, 1000 / MANUAL_HZ);

const padEl = $("pad");
const knob = $("knob");
function movePad(event) {
  const box = padEl.getBoundingClientRect();
  const r = box.width / 2;
  let dx = event.clientX - box.left - r;
  let dy = event.clientY - box.top - r;
  const len = Math.hypot(dx, dy);
  if (len > r) { dx = (dx / len) * r; dy = (dy / len) * r; }
  knob.style.left = `${r + dx - 24}px`;
  knob.style.top = `${r + dy - 24}px`;
  pad = { throttle: Math.round((-dy / r) * 100), steer: Math.round((dx / r) * 100) };
}
padEl.addEventListener("pointerdown", (e) => { padEl.setPointerCapture(e.pointerId); movePad(e); });
padEl.addEventListener("pointermove", (e) => { if (pad) movePad(e); });
const releasePad = () => { pad = null; knob.style.left = "56px"; knob.style.top = "56px"; };
padEl.addEventListener("pointerup", releasePad);
padEl.addEventListener("pointercancel", releasePad);
