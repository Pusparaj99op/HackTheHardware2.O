import { buildModeButtons, connectSocket, containRect, syncLabels, toImageCoords, toast } from "/static/common.js";

const $ = (id) => document.getElementById(id);
const SEND_WIDTH = 640;
const SEND_INTERVAL_MS = 66; // ~15 fps
const JPEG_QUALITY = 0.6;
const MAX_BUFFERED = 150_000;
const IMU_INTERVAL_MS = 100;

let state = null;
let sending = false;
let sentFrames = 0;
const imu = [];

const sock = connectSocket("/ws/phone", {
  onState: render,
  onError: toast,
  onStatus: (on) => $("dot").classList.toggle("on", on),
});
const setModes = buildModeButtons($("modes"), (mode) => sock.send({ type: "mode", mode }));

// ---------------------------------------------------------------- start (needs a user tap)
$("go").addEventListener("click", async () => {
  try {
    if (typeof DeviceMotionEvent !== "undefined" && DeviceMotionEvent.requestPermission) {
      await DeviceMotionEvent.requestPermission(); // iOS only; Android grants automatically
    }
    const stream = await navigator.mediaDevices.getUserMedia({
      audio: false,
      video: { facingMode: "environment", width: { ideal: 1280 }, height: { ideal: 720 } },
    });
    $("video").srcObject = stream;
    await $("video").play();
    await navigator.wakeLock?.request("screen").catch(() => null);
    $("start").hidden = true;
    startStreaming();
    startImu();
  } catch (err) {
    $("start-error").textContent =
      `Camera failed: ${err.message}. Use the https:// address and allow camera access.`;
  }
});

// ---------------------------------------------------------------- camera -> laptop
function startStreaming() {
  const video = $("video");
  const canvas = document.createElement("canvas");
  const ctx = canvas.getContext("2d");
  setInterval(() => {
    if (sending || !video.videoWidth || sock.buffered > MAX_BUFFERED) return;
    canvas.width = SEND_WIDTH;
    canvas.height = Math.round((SEND_WIDTH * video.videoHeight) / video.videoWidth);
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    sending = true;
    canvas.toBlob(
      (blob) => {
        if (blob) {
          sock.sendBinary(blob);
          sentFrames += 1;
        }
        sending = false;
      },
      "image/jpeg",
      JPEG_QUALITY,
    );
  }, SEND_INTERVAL_MS);
  setInterval(() => {
    $("fps").textContent = `${sentFrames} fps`;
    sentFrames = 0;
  }, 1000);
}

// ---------------------------------------------------------------- gyro -> laptop (odometry heading)
function startImu() {
  window.addEventListener("devicemotion", (e) => {
    const r = e.rotationRate;
    const g = e.accelerationIncludingGravity;
    if (!r || !g) return;
    imu.push([e.timeStamp, [r.alpha || 0, r.beta || 0, r.gamma || 0], [g.x || 0, g.y || 0, g.z || 0]]);
  });
  setInterval(() => {
    if (!imu.length) return;
    const batch = imu.splice(0);
    sock.send({ type: "imu", samples: batch.slice(-200) }); // server accepts at most 200
  }, IMU_INTERVAL_MS);
}

// ---------------------------------------------------------------- overlay
function drawOverlay() {
  const canvas = $("overlay");
  const video = $("video");
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (canvas.width !== Math.round(w * dpr)) {
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
  }
  const ctx = canvas.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (!state || !video.videoWidth) return;
  const r = containRect(w, h, video.videoWidth, video.videoHeight);
  const px = (x) => r.x + x * r.w;
  const py = (y) => r.y + y * r.h;
  ctx.font = "14px system-ui";
  for (const d of state.detections) {
    const focus = d.id != null && d.id === state.focus;
    ctx.strokeStyle = focus ? "#38d27a" : "#3e8bff";
    ctx.lineWidth = focus ? 4 : 2;
    const [x1, y1, x2, y2] = d.box;
    ctx.strokeRect(px(x1), py(y1), px(x2) - px(x1), py(y2) - py(y1));
    ctx.fillStyle = ctx.strokeStyle;
    ctx.fillText(`${d.label} #${d.id ?? "-"}`, px(x1) + 4, py(y1) + 16);
  }
  if (state.target.point) {
    const [tx, ty] = state.target.point;
    ctx.strokeStyle = "#e650e6";
    ctx.lineWidth = 3;
    ctx.beginPath();
    ctx.arc(px(tx), py(ty), 16, 0, Math.PI * 2);
    ctx.stroke();
  }
  if (state.marker) {
    const { x, y, heading } = state.marker;
    ctx.strokeStyle = "#28dcd6";
    ctx.lineWidth = 4;
    ctx.beginPath();
    ctx.moveTo(px(x), py(y));
    ctx.lineTo(px(x) + 50 * Math.cos(heading), py(y) + 50 * Math.sin(heading));
    ctx.stroke();
  }
}
(function loop() {
  drawOverlay();
  requestAnimationFrame(loop);
})();

// ---------------------------------------------------------------- UI
function render(s) {
  state = s;
  $("status").textContent = s.safety ? `STOP: ${s.safety} | ${s.status}` : s.status;
  const kill = $("kill");
  kill.textContent = s.killed ? "ARM (car is killed)" : "KILL";
  kill.classList.toggle("armed-off", s.killed);
  setModes(s.mode);
  syncLabels($("label"), s.labels);
  if (document.activeElement !== $("label")) $("label").value = s.target.label ?? "";
}

$("stage").addEventListener("click", (event) => {
  if (!$("start").hidden) return; // camera not started yet
  const video = $("video");
  const point = toImageCoords(event, video, video.videoWidth, video.videoHeight);
  if (point) sock.send({ type: "tap", x: point.x, y: point.y });
});
$("kill").addEventListener("click", () => sock.send({ type: state && !state.killed ? "kill" : "arm" }));
$("label").addEventListener("change", (e) => sock.send({ type: "target_class", label: e.target.value || null }));
$("clear").addEventListener("click", () => sock.send({ type: "clear_target" }));
