/**
 * static/js/app.js
 * Utilidades compartidas entre todas las páginas de CryptoAdvisor.
 */

// ─── RELOJ ────────────────────────────────────────────────────
function actualizarReloj() {
  const el = document.getElementById('header-clock');
  if (!el) return;
  const now = new Date();
  el.textContent = now.toLocaleString('es-PE', {
    weekday: 'short',
    year:    'numeric',
    month:   '2-digit',
    day:     '2-digit',
    hour:    '2-digit',
    minute:  '2-digit',
    second:  '2-digit'
  });
}

setInterval(actualizarReloj, 1000);
actualizarReloj();


// ─── TOAST ────────────────────────────────────────────────────
/**
 * Muestra una notificación flotante.
 * @param {string} mensaje  - Texto a mostrar
 * @param {string} tipo     - 'success' | 'error' | 'info'
 * @param {number} duracion - ms antes de desaparecer
 */
function mostrarToast(mensaje, tipo = 'info', duracion = 3500) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-${tipo}`;
  toast.textContent = mensaje;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transition = 'opacity 0.4s';
    setTimeout(() => toast.remove(), 400);
  }, duracion);
}


// ─── FETCH HELPER ─────────────────────────────────────────────
/**
 * Wrapper sobre fetch que maneja JSON y errores de red.
 * @param {string} url
 * @param {object} opciones - Opciones de fetch (method, body, etc.)
 * @returns {Promise<object>} - Respuesta JSON parseada
 */
async function apiPost(url, body = {}) {
  const response = await fetch(url, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json' },
    body:    JSON.stringify(body)
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.mensaje || `Error HTTP ${response.status}`);
  }
  return response.json();
}

async function apiGet(url) {
  const response = await fetch(url);
  if (!response.ok) throw new Error(`Error HTTP ${response.status}`);
  return response.json();
}


// ─── FORMATO ──────────────────────────────────────────────────
function formatearPrecio(precio) {
  return '$' + parseFloat(precio).toLocaleString('en-US', {
    minimumFractionDigits: 4,
    maximumFractionDigits: 4
  });
}

function formatearPct(valor) {
  return (parseFloat(valor) * 100).toFixed(2) + '%';
}