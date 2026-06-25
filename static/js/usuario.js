/**
 * static/js/usuario.js
<<<<<<< HEAD
 * Dashboard del usuario en CryptoAdvisor.
 * Incluye actualización automática del precio actual cada 60 segundos.
 */

let simboloSeleccionado = 'BTCUSDT';
let accionSeleccionada  = 'comprar';
let intervaloPrecioId   = null;
const PRECIO_REFRESH_MS = 60000; // Informe: actualización por defecto cada 60 segundos.

// ─── SELECTORES ───────────────────────────────────────────────
function seleccionarCripto(valor) {
  let btn = null;

  if (typeof valor === 'string') {
    simboloSeleccionado = valor.toUpperCase();
    btn = document.querySelector(`[data-symbol="${simboloSeleccionado}"]`);
  } else if (valor) {
    btn = valor;
    simboloSeleccionado = String(btn.dataset.symbol || 'BTCUSDT').toUpperCase();
  }

  document.querySelectorAll('.crypto-btn, .btn-cripto').forEach(b => {
    b.classList.remove('active');
    b.classList.remove('activo');
  });

  if (btn) {
    btn.classList.add('active');
    btn.classList.add('activo');
  }

  const base = simboloSeleccionado.replace('USDT', '');
  const symbolEl = document.getElementById('price-symbol');
  const priceEl = document.getElementById('price-value');
  if (symbolEl) symbolEl.textContent = base;
  if (priceEl) priceEl.textContent = '$—';

  actualizarPrecio(true);
=======
 * Lógica del dashboard del usuario en CryptoAdvisor.
 */

// Estado global del formulario
let simboloSeleccionado = 'BTCUSDT';
let accionSeleccionada  = 'comprar';


// ─── SELECTORES ───────────────────────────────────────────────
function seleccionarCripto(btn) {
  document.querySelectorAll('.crypto-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  simboloSeleccionado = btn.dataset.symbol;

  // Actualizar precio en tarjeta
  const base = simboloSeleccionado.replace('USDT', '');
  document.getElementById('price-symbol').textContent = base;
  document.getElementById('price-value').textContent = '$—';
  actualizarPrecio();
>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
}

function seleccionarAccion(btn) {
  document.querySelectorAll('.action-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  accionSeleccionada = btn.dataset.accion;
}

<<<<<<< HEAD
// ─── PRECIO EN VIVO ───────────────────────────────────────────
async function actualizarPrecio(manual = false) {
  const el = document.getElementById('price-value');
  const updatedEl = document.getElementById('price-updated-at');
  if (!el) return;

  try {
    if (manual) {
      el.textContent = 'Actualizando...';
    }

    const data = await apiGet(`/api/precio/${simboloSeleccionado}`);

    if (data.ok && data.datos) {
      el.textContent = formatearPrecio(data.datos.precio);
      el.style.color = 'var(--green)';

      if (updatedEl) {
        const ahora = new Date();
        updatedEl.textContent = `Actualizado: ${ahora.toLocaleTimeString('es-PE')} · Auto cada 60s`;
      }

      setTimeout(() => {
        el.style.color = 'var(--accent)';
      }, 900);
    } else {
      throw new Error(data.mensaje || 'Respuesta inválida del servidor');
    }
  } catch (err) {
    el.textContent = '$ (sin datos)';
    if (updatedEl) updatedEl.textContent = 'No se pudo actualizar el precio';
=======

// ─── PRECIO EN VIVO ───────────────────────────────────────────
async function actualizarPrecio() {
  const el = document.getElementById('price-value');
  if (!el) return;

  try {
    const data = await apiGet(`/api/precio/${simboloSeleccionado}`);
    if (data.ok) {
      el.textContent = formatearPrecio(data.datos.precio);
      el.style.color = 'var(--green)';
      setTimeout(() => { el.style.color = 'var(--accent)'; }, 1000);
    }
  } catch (err) {
    el.textContent = '$ (sin datos)';
>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
    console.warn('[Usuario] No se pudo obtener precio:', err.message);
  }
}

<<<<<<< HEAD
function iniciarActualizacionAutomaticaPrecio() {
  if (intervaloPrecioId) {
    clearInterval(intervaloPrecioId);
  }

  actualizarPrecio(true);

  intervaloPrecioId = setInterval(() => {
    // Evita llamadas innecesarias si la pestaña está en segundo plano.
    if (!document.hidden) {
      actualizarPrecio(false);
    }
  }, PRECIO_REFRESH_MS);
}
=======
>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901

// ─── EJECUTAR ANÁLISIS ────────────────────────────────────────
async function ejecutarAnalisis() {
  const btnAnalizar = document.getElementById('btn-analizar');
  const loading     = document.getElementById('loading');
  const resultado   = document.getElementById('resultado-section');

<<<<<<< HEAD
=======
  // Mostrar loading
>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
  btnAnalizar.disabled = true;
  loading.classList.remove('hidden');
  resultado.classList.add('hidden');

  try {
    const perfilEl = document.getElementById('perfil-riesgo');
    const data = await apiPost('/api/analizar', {
      symbol: simboloSeleccionado,
      accion: accionSeleccionada,
      perfil_riesgo: perfilEl ? perfilEl.value : 'moderado'
    });

    if (!data.ok) throw new Error(data.mensaje);

    mostrarResultado(data.datos);
<<<<<<< HEAD
    mostrarToast('✅ Análisis completado y guardado en historial', 'success');
    actualizarPrecio(false);
=======
    mostrarToast('✅ Análisis completado y enviado al administrador', 'success');
>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901

  } catch (err) {
    mostrarToast(`❌ Error: ${err.message}`, 'error', 5000);
    console.error('[Usuario] Error en análisis:', err);
  } finally {
    btnAnalizar.disabled = false;
    loading.classList.add('hidden');
  }
}

<<<<<<< HEAD
=======

>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
// ─── MOSTRAR RESULTADO ────────────────────────────────────────
function mostrarResultado(datos) {
  const { mercado, prediccion, operacion_id, aviso_legal } = datos;

<<<<<<< HEAD
=======
  // Datos de mercado
>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
  document.getElementById('res-precio').textContent =
    formatearPrecio(mercado.precio_actual);

  const cambio = parseFloat(mercado.cambio_pct);
  const cambioEl = document.getElementById('res-cambio');
  cambioEl.textContent = (cambio >= 0 ? '+' : '') + cambio.toFixed(2) + '%';
  cambioEl.style.color = cambio >= 0 ? 'var(--green)' : 'var(--red)';

  const tendMap = { alcista: '🟢 Alcista', bajista: '🔴 Bajista', lateral: '🟡 Lateral' };
  document.getElementById('res-tendencia').textContent =
    tendMap[mercado.tendencia] || mercado.tendencia;

  document.getElementById('res-volumen').textContent =
    mercado.volumen.charAt(0).toUpperCase() + mercado.volumen.slice(1);

  document.getElementById('res-volatilidad').textContent =
    mercado.volatilidad.charAt(0).toUpperCase() + mercado.volatilidad.slice(1);

  const indicadores = mercado.indicadores || {};
  document.getElementById('res-rsi').textContent =
    indicadores.rsi14 !== undefined ? Number(indicadores.rsi14).toFixed(2) : '—';
  document.getElementById('res-macd').textContent =
    indicadores.macd_histogram !== undefined ? Number(indicadores.macd_histogram).toFixed(6) : '—';
  document.getElementById('res-vwap').textContent =
    indicadores.vwap !== undefined ? formatearPrecio(indicadores.vwap) : '—';
  document.getElementById('res-liquidez').textContent =
    mercado.liquidez_24h_usdt !== undefined ? formatearPrecio(mercado.liquidez_24h_usdt) : '—';

<<<<<<< HEAD
  const pct = prediccion.probabilidad_pct;
  const circle = document.getElementById('circle-fill');
  const circunferencia = 314;
  const offset = circunferencia - (circunferencia * pct / 100);
  circle.style.strokeDashoffset = offset;

  document.getElementById('prob-pct').textContent = pct.toFixed(1) + '%';

  const badge = document.getElementById('confianza-badge');
  badge.textContent = prediccion.confianza || '—';
  badge.className = 'confianza-badge ' + (prediccion.color || '');

  document.getElementById('recomendacion').textContent =
    'Recomendación: ' + (prediccion.recomendacion || 'HOLD');

  const probs = prediccion.probabilidades || {};
  document.getElementById('probabilidades-detalle').textContent =
    `BUY ${(Number(probs.BUY || 0) * 100).toFixed(1)}% · ` +
    `SELL ${(Number(probs.SELL || 0) * 100).toFixed(1)}% · ` +
    `HOLD ${(Number(probs.HOLD || 0) * 100).toFixed(1)}%`;

  const warningEl = document.getElementById('volatilidad-warning');
  if (datos.advertencia) {
    warningEl.textContent = datos.advertencia;
    warningEl.classList.remove('hidden');
  } else {
    warningEl.classList.add('hidden');
  }

  document.getElementById('aviso-legal').textContent =
    aviso_legal || 'Este sistema no ofrece asesoramiento financiero. Invierta con responsabilidad.';

  document.getElementById('operacion-id').textContent =
    'ID: #' + operacion_id;

  document.getElementById('resultado-section').classList.remove('hidden');
  document.getElementById('resultado-section').scrollIntoView({ behavior: 'smooth' });
}

// ─── PERFIL DE RIESGO ─────────────────────────────────────────
async function guardarPerfilRiesgo() {
  const perfilEl = document.getElementById('perfil-riesgo');
  if (!perfilEl) return;
  try {
    await apiPost('/api/perfil-riesgo', { perfil_riesgo: perfilEl.value });
    mostrarToast('Perfil de riesgo actualizado', 'success');
  } catch (err) {
    mostrarToast('No se pudo actualizar el perfil', 'error');
  }
}

// ─── INICIALIZACIÓN ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  const primerBoton = document.querySelector('.btn-cripto, .crypto-btn');
  if (primerBoton && primerBoton.dataset.symbol) {
    seleccionarCripto(primerBoton.dataset.symbol);
  } else {
    iniciarActualizacionAutomaticaPrecio();
  }

  const perfilEl = document.getElementById('perfil-riesgo');
  if (perfilEl) perfilEl.addEventListener('change', guardarPerfilRiesgo);

  document.addEventListener('visibilitychange', () => {
    if (!document.hidden) {
      actualizarPrecio(false);
    }
  });
});
=======

  // Probabilidad circular
  const pct   = prediccion.probabilidad_pct;
  const circle = document.getElementById('circle-fill');
  const circunferencia = 314; // 2π × 50
  const offset = circunferencia - (pct / 100) * circunferencia;

  // Color de la barra según probabilidad
  if (pct >= 65) {
    circle.style.stroke = 'var(--green)';
  } else if (pct >= 45) {
    circle.style.stroke = 'var(--yellow)';
  } else {
    circle.style.stroke = 'var(--red)';
  }

  setTimeout(() => {
    circle.style.strokeDashoffset = offset;
  }, 100);

  document.getElementById('prob-pct').textContent = pct.toFixed(1) + '%';

  // Confianza badge
  const badgeEl = document.getElementById('confianza-badge');
  const confMap = { Alta: 'confianza-alta', Media: 'confianza-media', Baja: 'confianza-baja' };
  badgeEl.className = `confianza-badge ${confMap[prediccion.confianza] || ''}`;
  badgeEl.textContent = `Confianza: ${prediccion.confianza}`;

  document.getElementById('recomendacion').textContent = prediccion.recomendacion;

  const probs = prediccion.probabilidades || {};
  const probsEl = document.getElementById('probabilidades-detalle');
  if (probsEl) {
    probsEl.textContent = `BUY ${(Number(probs.BUY || 0) * 100).toFixed(1)}% · SELL ${(Number(probs.SELL || 0) * 100).toFixed(1)}% · HOLD ${(Number(probs.HOLD || 0) * 100).toFixed(1)}%`;
  }

  const warningEl = document.getElementById('volatilidad-warning');
  if (mercado.advertencia_volatilidad) {
    warningEl.textContent = mercado.aviso_volatilidad || 'Advertencia: volatilidad extrema detectada.';
    warningEl.classList.remove('hidden');
  } else {
    warningEl.textContent = '';
    warningEl.classList.add('hidden');
  }

  const legalEl = document.getElementById('aviso-legal');
  if (legalEl && aviso_legal) legalEl.textContent = aviso_legal;


  // Estado
  document.getElementById('operacion-id').textContent = `ID de operación: #${operacion_id}`;

  // Mostrar sección
  const seccion = document.getElementById('resultado-section');
  seccion.classList.remove('hidden');

  // Scroll al resultado
  setTimeout(() => {
    seccion.scrollIntoView({ behavior: 'smooth', block: 'start' });
  }, 200);
}


// ─── INICIALIZACIÓN ───────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  actualizarPrecio();

  // Auto-actualizar precio cada 30 segundos
  setInterval(actualizarPrecio, 30000);

  // Toast container (si no existe en el HTML lo creamos)
  if (!document.getElementById('toast-container')) {
    const tc = document.createElement('div');
    tc.id = 'toast-container';
    tc.className = 'toast-container';
    document.body.appendChild(tc);
  }
});
>>>>>>> a3f45dd4a041dd5031a44a3731b083b9b7932901
