/**
 * Landing runv.club — carrega members.json (só dados públicos) e coloca
 * pontos clicáveis (links) fora da coluna de texto; brilho ligado à data since.
 * Array vazio: sem estrelas até build_directory.py gerar o JSON a partir de users.json.
 */

function hashUsername(s) {
  let h = 2166136261;
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i);
    h = Math.imul(h, 16777619);
  }
  return h >>> 0;
}

function parseSince(iso) {
  if (!iso) return 0;
  const t = Date.parse(iso);
  return Number.isFinite(t) ? t : 0;
}

function starBrightness(sinceMs) {
  const now = Date.now();
  const age = Math.max(0, now - sinceMs);
  const halfYear = 180 * 24 * 3600 * 1000;
  const t = Math.exp(-age / halfYear);
  return 0.25 + 0.75 * t;
}

function seededPoint(w, h, seed) {
  const x = (Math.sin(seed * 0.001) * 43758.5453) % 1;
  const y = (Math.cos(seed * 0.002) * 23421.6789) % 1;
  const nx = ((x < 0 ? -x : x) * 0.85 + 0.075) * w;
  const ny = ((y < 0 ? -y : y) * 0.85 + 0.075) * h;
  return { x: nx, y: ny };
}

/** Expande o rect em px (viewport) para manter margem em relação ao texto. */
function inflateRect(r, pad) {
  return {
    left: r.left - pad,
    top: r.top - pad,
    right: r.right + pad,
    bottom: r.bottom + pad,
  };
}

function pointInRect(x, y, rect) {
  return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
}

/**
 * Posição para um ponto: fora da coluna `.wrap` (texto), com fallback para
 * faixas laterais ou cantos quando o ecrã é estreito.
 */
function findStarPosition(w, h, seed, exclude) {
  const edge = 14;
  for (let attempt = 0; attempt < 140; attempt++) {
    const s = seed + attempt * 9973;
    const { x, y } = seededPoint(w, h, s);
    const px = Math.max(edge, Math.min(w - edge, x));
    const py = Math.max(edge, Math.min(h - edge, y));
    if (!pointInRect(px, py, exclude)) return { x: px, y: py };
  }

  const spaceLeft = Math.max(0, exclude.left - edge);
  const spaceRight = Math.max(0, w - exclude.right - edge);
  const spaceAbove = Math.max(0, exclude.top - edge);
  const spaceBelow = Math.max(0, h - exclude.bottom - edge);
  const order = [
    [spaceLeft, "left"],
    [spaceRight, "right"],
    [spaceAbove, "above"],
    [spaceBelow, "below"],
  ].sort((a, b) => b[0] - a[0]);

  const yJitter = edge + ((seed >>> 5) % Math.max(1, h - 2 * edge));
  const xJitter = edge + ((seed >>> 9) % Math.max(1, w - 2 * edge));

  for (const [, side] of order) {
    if (side === "left" && spaceLeft > 6)
      return { x: edge + spaceLeft * 0.45, y: yJitter };
    if (side === "right" && spaceRight > 6)
      return { x: exclude.right + spaceRight * 0.55, y: yJitter };
    if (side === "above" && spaceAbove > 6)
      return { x: xJitter, y: edge + spaceAbove * 0.45 };
    if (side === "below" && spaceBelow > 6)
      return { x: xJitter, y: exclude.bottom + spaceBelow * 0.55 };
  }

  const cornerX = seed % 2 === 0 ? edge : w - edge;
  const cornerY = (seed >>> 3) % 2 === 0 ? edge : h - edge;
  return { x: cornerX, y: cornerY };
}

function validMembers(members) {
  return members.filter(
    (m) =>
      m &&
      typeof m.username === "string" &&
      m.username.length > 0 &&
      typeof m.path === "string" &&
      m.path.length > 0
  );
}

function renderStarLinks(container, wrapEl, members) {
  if (!container) return;

  container.replaceChildren();

  const w = window.innerWidth;
  const h = window.innerHeight;
  if (w < 32 || h < 32) return;

  const pad = 36;
  const exclude = wrapEl
    ? inflateRect(wrapEl.getBoundingClientRect(), pad)
    : { left: 0, top: 0, right: w, bottom: h };

  for (const m of validMembers(members)) {
    const seed = hashUsername(m.username);
    const { x, y } = findStarPosition(w, h, seed, exclude);
    const bright = starBrightness(parseSince(m.since));

    const a = document.createElement("a");
    a.className = "star-member";
    a.href = m.path;
    a.setAttribute("aria-label", `Site de ~${m.username}`);
    a.textContent = `~${m.username}`;
    a.style.left = `${x}px`;
    a.style.top = `${y}px`;
    a.style.opacity = String(0.55 + bright * 0.43);
    const scale = 0.78 + bright * 0.42;
    a.style.setProperty("--star-scale", String(scale));

    container.appendChild(a);
  }
}

async function main() {
  const starRoot = document.getElementById("starfield");
  const wrapEl = document.querySelector(".wrap");

  let members = [];

  try {
    const res = await fetch("data/members.json", { cache: "no-store" });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    members = await res.json();
    if (!Array.isArray(members)) throw new Error("members.json inválido");
  } catch {
    members = [];
  }

  let starRaf = 0;
  const scheduleStars = () => {
    if (!starRoot) return;
    cancelAnimationFrame(starRaf);
    starRaf = requestAnimationFrame(() => {
      renderStarLinks(starRoot, wrapEl, members);
    });
  };

  scheduleStars();

  window.addEventListener("resize", scheduleStars, { passive: true });
  window.addEventListener("scroll", scheduleStars, { passive: true, capture: true });
  if (typeof ResizeObserver !== "undefined" && wrapEl) {
    const ro = new ResizeObserver(scheduleStars);
    ro.observe(wrapEl);
  }
}

document.addEventListener("DOMContentLoaded", main);
