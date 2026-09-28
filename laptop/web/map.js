// Top-down map of the car's path memory. World metres: +x = start heading (up), +y = left.

const GRID_M = 0.5;
const MIN_SPAN_M = 3;

function bounds(points) {
  let minX = -MIN_SPAN_M / 2, maxX = MIN_SPAN_M / 2, minY = -MIN_SPAN_M / 2, maxY = MIN_SPAN_M / 2;
  for (const [x, y] of points) {
    minX = Math.min(minX, x); maxX = Math.max(maxX, x);
    minY = Math.min(minY, y); maxY = Math.max(maxY, y);
  }
  return { minX, maxX, minY, maxY };
}

// World (x forward, y left) -> screen (forward = up, left = left).
function projector(canvas, b) {
  const pad = 30;
  const spanX = b.maxX - b.minX;
  const spanY = b.maxY - b.minY;
  const scale = Math.min((canvas.height - 2 * pad) / spanX, (canvas.width - 2 * pad) / spanY);
  const cx = (b.minX + b.maxX) / 2;
  const cy = (b.minY + b.maxY) / 2;
  return {
    scale,
    at: ([x, y]) => [canvas.width / 2 - (y - cy) * scale, canvas.height / 2 - (x - cx) * scale],
  };
}

function drawGrid(ctx, canvas, b, p) {
  ctx.strokeStyle = "#1a2028";
  ctx.lineWidth = 1;
  for (let x = Math.floor(b.minX / GRID_M) * GRID_M; x <= b.maxX + GRID_M; x += GRID_M) {
    const [, sy] = p.at([x, 0]);
    ctx.beginPath(); ctx.moveTo(0, sy); ctx.lineTo(canvas.width, sy); ctx.stroke();
  }
  for (let y = Math.floor(b.minY / GRID_M) * GRID_M; y <= b.maxY + GRID_M; y += GRID_M) {
    const [sx] = p.at([0, y]);
    ctx.beginPath(); ctx.moveTo(sx, 0); ctx.lineTo(sx, canvas.height); ctx.stroke();
  }
}

function drawPath(ctx, points, p, style, width, dash = []) {
  if (points.length < 2) return;
  ctx.strokeStyle = style;
  ctx.lineWidth = width;
  ctx.setLineDash(dash);
  ctx.beginPath();
  points.forEach((pt, i) => {
    const [sx, sy] = p.at(pt);
    if (i === 0) ctx.moveTo(sx, sy); else ctx.lineTo(sx, sy);
  });
  ctx.stroke();
  ctx.setLineDash([]);
}

function drawCar(ctx, pose, p) {
  const [sx, sy] = p.at([pose[0], pose[1]]);
  const angle = -pose[2] - Math.PI / 2; // world theta (CCW from +x/up) -> canvas angle
  ctx.save();
  ctx.translate(sx, sy);
  ctx.rotate(angle);
  ctx.fillStyle = "#3e8bff";
  ctx.beginPath();
  ctx.moveTo(16, 0); ctx.lineTo(-10, -9); ctx.lineTo(-6, 0); ctx.lineTo(-10, 9);
  ctx.closePath();
  ctx.fill();
  ctx.restore();
}

export function drawMap(canvas, state) {
  const ctx = canvas.getContext("2d");
  const trail = state.trail || [];
  const ghost = state.ghost || [];
  const pose = state.pose || [0, 0, 0];
  const b = bounds([...trail, ...ghost, [pose[0], pose[1]]]);
  const p = projector(canvas, b);
  ctx.fillStyle = "#080a0c";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  drawGrid(ctx, canvas, b, p);
  drawPath(ctx, ghost, p, "#5d6673", 3, [8, 6]);
  drawPath(ctx, trail, p, "#35e0c8", 3);
  if (trail.length) {
    const [sx, sy] = p.at(trail[0]);
    ctx.fillStyle = "#38d27a";
    ctx.beginPath(); ctx.arc(sx, sy, 6, 0, Math.PI * 2); ctx.fill();
  }
  ctx.strokeStyle = "#ff4d4f";
  ctx.lineWidth = 3;
  for (const bump of state.bumps || []) {
    const [sx, sy] = p.at(bump);
    ctx.beginPath();
    ctx.moveTo(sx - 7, sy - 7); ctx.lineTo(sx + 7, sy + 7);
    ctx.moveTo(sx + 7, sy - 7); ctx.lineTo(sx - 7, sy + 7);
    ctx.stroke();
  }
  drawCar(ctx, pose, p);
  ctx.fillStyle = "#8a94a3";
  ctx.font = "13px system-ui";
  ctx.fillText(`grid ${GRID_M} m`, 10, canvas.height - 10);
}
