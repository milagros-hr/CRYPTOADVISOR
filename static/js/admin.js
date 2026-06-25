/**
 * static/js/admin.js
 * Lógica del panel de administrador en CryptoAdvisor.
 */

// ─── ESTADO DEL MODAL ─────────────────────────────────────────
let accionPendiente   = null;  // 'aprobar' | 'rechazar'
let operacionPendiente = null; // ID de la operación

// ─── APROBAR / RECHAZAR ───────────────────────────────────────
function aprobar(operacionId) {
  accionPendiente    = 'aprobar';
  operacionPendiente = operacionId;

  document.getElementById('modal-title').textContent    = '✅ Confirmar Aprobación';
  document.getElementById('modal-desc').textContent     = `¿Aprobar la operación #${operacionId}? Agrega una nota opcional:`;
  document.getElementById('modal-nota').value           = '';
  document.getElementById('modal-confirm-btn').className = 'btn btn-success';
  document.getElementById('modal-confirm-btn').textContent = 'Aprobar';

  abrirModal();
}

function rechazar(operacionId) {
  accionPendiente    = 'rechazar';
  operacionPendiente = operacionId;

  document.getElementById('modal-title').textContent    = '❌ Confirmar Rechazo';
  document.getElementById('modal-desc').textContent     = `¿Rechazar la operación #${operacionId}? Indica el motivo:`;
  document.getElementById('modal-nota').value           = '';
  document.getElementById('modal-confirm-btn').className = 'btn btn-danger';
  document.getElementById('modal-confirm-btn').textContent = 'Rechazar';

  abrirModal();
}

// ─── MODAL ────────────────────────────────────────────────────
function abrirModal() {
  document.getElementById('modal-overlay').classList.remove('hidden');
}

function cerrarModal() {
  document.getElementById('modal-overlay').classList.add('hidden');
  accionPendiente    = null;
  operacionPendiente = null;
}

async function confirmarAccion() {
  if (!accionPendiente || !operacionPendiente) return;

  const nota = document.getElementById('modal-nota').value.trim() ||
    (accionPendiente === 'aprobar'
      ? 'Aprobada por el administrador.'
      : 'Rechazada por el administrador.');

  const url = `/api/admin/${accionPendiente === 'aprobar' ? 'aprobar' : 'rechazar'}/${operacionPendiente}`;

  try {
    const data = await apiPost(url, { nota });

    if (data.ok) {
      // Eliminar la fila de la tabla
      const fila = document.getElementById(`row-${operacionPendiente}`);
      if (fila) {
        fila.style.transition = 'opacity 0.4s, transform 0.4s';
        fila.style.opacity    = '0';
        fila.style.transform  = 'translateX(-20px)';
        setTimeout(() => fila.remove(), 400);
      }

      const tipo = accionPendiente === 'aprobar' ? 'success' : 'error';
      mostrarToast(data.mensaje, tipo);

      // Actualizar contador
      actualizarContadorPendientes();

    } else {
      mostrarToast(`Error: ${data.mensaje}`, 'error');
    }

  } catch (err) {
    mostrarToast(`❌ Error de conexión: ${err.message}`, 'error');
    console.error('[Admin] Error en acción:', err);
  } finally {
    cerrarModal();
  }
}

// ─── ACTUALIZAR CONTADOR ──────────────────────────────────────
function actualizarContadorPendientes() {
  const filas = document.querySelectorAll('#tbody-pendientes tr');
  const contador = document.getElementById('count-pendientes');
  if (contador) contador.textContent = filas.length;

  // Si no quedan filas, mostrar empty state
  if (filas.length === 0) {
    const tabla = document.getElementById('tabla-pendientes');
    if (tabla) {
      tabla.innerHTML = `
        <div class="empty-state" id="empty-pendientes">
          <div class="empty-icon">🎉</div>
          <h3>No hay solicitudes pendientes</h3>
          <p>Todas las operaciones han sido procesadas</p>
        </div>
      `;
    }
  }
}

// ─── RECARGAR PENDIENTES (vía API) ────────────────────────────
async function recargarPendientes() {
  try {
    const data = await apiGet('/api/admin/pendientes');
    if (!data.ok) throw new Error(data.mensaje);

    const pendientes = data.datos;
    const tbody = document.getElementById('tbody-pendientes');
    const contEl = document.getElementById('count-pendientes');

    if (contEl) contEl.textContent = pendientes.length;

    if (!tbody) return;

    if (pendientes.length === 0) {
      actualizarContadorPendientes();
      return;
    }

    // Marcar IDs ya existentes en la tabla
    const idsExistentes = new Set(
      [...document.querySelectorAll('#tbody-pendientes tr')].map(r =>
        parseInt(r.id.replace('row-', ''))
      )
    );

    pendientes.forEach(op => {
      if (!idsExistentes.has(op.id)) {
        // Insertar nueva fila
        const tr = document.createElement('tr');
        tr.id = `row-${op.id}`;
        tr.innerHTML = `
          <td><span class="op-id">#${op.id}</span></td>
          <td>${op.username}</td>
          <td><span class="cripto-tag">${op.cripto.replace('USDT','')}</span></td>
          <td>
            <span class="accion-badge accion-${op.accion}">
              ${ { comprar:'📈 Comprar', vender:'📉 Vender', esperar:'⏳ Esperar' }[op.accion] || op.accion }
            </span>
          </td>
          <td>$${parseFloat(op.precio_actual).toFixed(4)}</td>
          <td>
            <div class="prob-bar-container">
              <div class="prob-bar" style="width:${Math.round(op.probabilidad*100)}%"></div>
              <span>${(op.probabilidad*100).toFixed(1)}%</span>
            </div>
          </td>
          <td>
            <span class="tendencia-${op.tendencia}">
              ${ { alcista:'🟢 Alcista', bajista:'🔴 Bajista', lateral:'🟡 Lateral' }[op.tendencia] || op.tendencia }
            </span>
          </td>
          <td>${op.volumen.charAt(0).toUpperCase()+op.volumen.slice(1)}</td>
          <td>${op.volatilidad.charAt(0).toUpperCase()+op.volatilidad.slice(1)}</td>
          <td class="date-col">${op.created_at.slice(0,16)}</td>
          <td class="actions-col">
            <button class="btn btn-xs btn-success" onclick="aprobar(${op.id})">✓ Aprobar</button>
            <button class="btn btn-xs btn-danger"  onclick="rechazar(${op.id})">✕ Rechazar</button>
          </td>
        `;
        tbody.prepend(tr);
        mostrarToast(`Nueva solicitud #${op.id} de ${op.username}`, 'info');
      }
    });

  } catch (err) {
    mostrarToast(`Error actualizando: ${err.message}`, 'error');
  }
}

// ─── CERRAR MODAL CON ESC ─────────────────────────────────────
document.addEventListener('keydown', function (e) {
  if (e.key === 'Escape') cerrarModal();
});

// ─── AUTO-REFRESH CADA 30s ────────────────────────────────────
document.addEventListener('DOMContentLoaded', function () {
  setInterval(recargarPendientes, 30000);
});