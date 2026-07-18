let extractosData = [];

document.addEventListener('DOMContentLoaded', cargarExtractos);

const uploadCard = document.getElementById('upload-card');
uploadCard.addEventListener('dragover', e => { e.preventDefault(); uploadCard.classList.add('drag-over'); });
uploadCard.addEventListener('dragleave', () => uploadCard.classList.remove('drag-over'));
uploadCard.addEventListener('drop', e => {
    e.preventDefault();
    uploadCard.classList.remove('drag-over');
    if (e.dataTransfer.files.length > 0) subirPDF(e.dataTransfer.files[0]);
});

function subirPDF(file) {
    if (!file || !file.name.toLowerCase().endsWith('.pdf')) {
        alert('Solo se aceptan archivos PDF');
        return;
    }
    document.getElementById('upload-card').style.display = 'none';
    document.getElementById('upload-result').style.display = 'none';
    document.getElementById('upload-progress').style.display = 'block';
    const statusEl = document.getElementById('upload-status');
    const subEl = document.getElementById('upload-substatus');
    const msgs = ['Desbloqueando PDF', 'Identificando banco', 'Extrayendo transacciones', 'Generando base de datos'];
    let idx = 0;
    statusEl.textContent = msgs[0] + '...';
    subEl.textContent = '';
    const intervalId = setInterval(() => {
        idx = (idx + 1) % msgs.length;
        statusEl.textContent = msgs[idx] + '...';
    }, 1800);
    const formData = new FormData();
    formData.append('pdf', file);
    fetch('/api/upload-pdf', { method: 'POST', body: formData })
        .then(r => r.json().then(data => ({status: r.status, data})))
        .then(({status, data}) => {
            clearInterval(intervalId);
            document.getElementById('upload-progress').style.display = 'none';
            if (status === 409) { document.getElementById('upload-card').style.display = 'block'; alert('Este extracto ya existe en la base de datos'); return; }
            if (status !== 200) { document.getElementById('upload-card').style.display = 'block'; alert('Error: ' + (data.error || 'Error desconocido')); return; }
            const resultDiv = document.getElementById('upload-result');
            if (data.success) {
                const tipoLabel = data.tipo === 'tarjeta_credito' ? 'Tarjeta de Crédito' : 'Cuenta Corriente';
                let logsHtml = '';
                if (data.logs && data.logs.length > 0) {
                    logsHtml = `<div style="margin-top:8px"><strong>Proceso:</strong><pre class=\"upload-logs\">${data.logs.join('\n')}</pre></div>`;
                }
                resultDiv.innerHTML = `<div class="result-ok"><span class="result-icon">✅</span><div class="result-info"><strong>${data.archivo_original}</strong><p>Banco: ${data.banco} | Período: ${data.periodo} | Tipo: ${tipoLabel}</p></div></div>` + logsHtml;
                resultDiv.style.display = 'block';
                cargarExtractos();
                document.getElementById('upload-card').style.display = 'block';
            } else {
                let errHtml = `<div class="result-error">❌ Error procesando el PDF</div>`;
                if (data.error) errHtml += `<div class="result-error-detail">${data.error}</div>`;
                if (data.logs && data.logs.length > 0) errHtml += `<div style="margin-top:8px"><strong>Logs:</strong><pre class=\"upload-logs\">${data.logs.join('\n')}</pre></div>`;
                resultDiv.innerHTML = errHtml;
                resultDiv.style.display = 'block';
                document.getElementById('upload-card').style.display = 'block';
            }
        })
        .catch(err => {
            clearInterval(intervalId);
            document.getElementById('upload-progress').style.display = 'none';
            document.getElementById('upload-card').style.display = 'block';
            alert('Error de conexión: ' + err);
        });
}

function cargarExtractos() {
    const container = document.getElementById('extractos-list');
    container.innerHTML = '<div class="extractos-loading">Cargando extractos...</div>';
    fetch('/api/extractos')
        .then(r => r.json())
        .then(data => {
            extractosData = data;
            if (data.length === 0) { container.innerHTML = '<div class="extractos-loading">No hay extractos cargados</div>'; return; }
            const grupos = {};
            data.forEach(e => { const key = e.fuente || 'desconocido'; if (!grupos[key]) grupos[key] = []; grupos[key].push(e); });
const orden = ['nequi', 'nu', 'rappicard', 'dale', 'daviplata'];
const nombres = {nequi: 'Nequi', nu: 'Nu Bank', rappicard: 'RappiCard / Davivienda', dale: 'Dale', daviplata: 'Daviplata'};
            let html = '';
            orden.forEach(banco => {
                if (!grupos[banco]) return;
                html += `<div class="banco-grupo"><h3 class="banco-titulo">${nombres[banco] || banco} <span class="banco-count">${grupos[banco].length} extractos</span></h3><div class="banco-lista">`;
                grupos[banco].forEach(e => {
                    const tipo = e.tipo === 'tarjeta_credito' ? '💳' : '🏦';
                    html += `<div class="extracto-item" onclick="abrirDetalle(${e.id})"><span class="extracto-icono">${tipo}</span><div class="extracto-info"><span class="extracto-periodo">${e.periodo || '—'}</span><span class="extracto-titular">${e.titular || ''}</span></div><span class="extracto-txs">${e.num_transacciones || 0} tx</span></div>`;
                });
                html += '</div></div>';
            });
            container.innerHTML = html;
        })
        .catch(() => { container.innerHTML = '<div class="extractos-loading">Error cargando extractos</div>'; });
}

function formatPesos(val) {
    if (val == null) return '—';
    const s = Math.abs(val).toLocaleString('es-CO', {minimumFractionDigits: 0});
    return val < 0 ? `-$${s}` : `$${s}`;
}

function abrirDetalle(id) {
    document.getElementById('detalle-modal').style.display = 'flex';
    document.getElementById('detalle-body').innerHTML = '<div class="detalle-loading">Cargando...</div>';
    fetch(`/api/extracto/${id}`)
        .then(r => r.json())
        .then(d => {
            const isTC = d.es_tarjeta_credito;
            const tipoIcon = isTC ? '💳' : '🏦';
            const nombresBanco = {nequi: 'Nequi', nu: 'Nu Bank', rappicard: 'RappiCard', dale: 'Dale', daviplata: 'Daviplata'};
            const nombreBanco = nombresBanco[d.fuente] || d.fuente;
            document.getElementById('detalle-titulo').textContent = `${tipoIcon} ${nombreBanco} — ${d.periodo}`;

            let html = '';

            html += `<div class="detalle-info"><div class="detalle-info-row"><span class="detalle-label">Archivo</span><span class="detalle-valor">${d.archivo}</span></div>`;
            html += `<div class="detalle-info-row"><span class="detalle-label">Titular</span><span class="detalle-valor">${d.titular || '—'}</span></div>`;
            html += `<div class="detalle-info-row"><span class="detalle-label">Transacciones</span><span class="detalle-valor">${d.num_transacciones}</span></div></div>`;

            if (isTC && d.tc_meta) {
                const tc = d.tc_meta;
                html += `<div class="detalle-tc"><h4 class="detalle-subtitle">💳 Información de la Tarjeta</h4><div class="tc-grid">`;
                const rows = [
                    ['Total a Pagar', tc.total_pagar_fmt, 'highlight'],
                    ['Pago Mínimo', tc.pago_minimo_fmt, ''],
                    ['Saldo Anterior', tc.saldo_anterior_fmt, ''],
                    ['Saldo Actual', tc.saldo_actual_fmt, ''],
                    ['Cupo Total', tc.cupo_total_fmt, ''],
                    ['Total Cargos', formatPesos(d.total_gastos), ''],
                    ['Total Abonos', formatPesos(d.total_ingresos), ''],
                    ['Fecha de Corte', tc.fecha_corte || '—', ''],
                    ['Fecha de Pago', tc.fecha_pago || '—', ''],
                ];
                rows.forEach(r => {
                    html += `<div class="tc-item ${r[2]}"><span class="tc-label">${r[0]}</span><span class="tc-valor">${r[1]}</span></div>`;
                });
                html += `</div></div>`;
            }

            if (d.num_cuotas > 0) {
                html += `<div class="detalle-cuotas"><h4 class="detalle-subtitle">🔄 Compras en Cuotas (${d.num_cuotas} grupos)</h4>`;
                const cuotasAgrupadas = {};
                d.transacciones.filter(t => t.es_cuota).forEach(t => {
                    const key = t.descripcion.trim().toLowerCase();
                    if (!cuotasAgrupadas[key]) cuotasAgrupadas[key] = [];
                    cuotasAgrupadas[key].push(t);
                });
                Object.values(cuotasAgrupadas).forEach(grupo => {
                    const totalCuotas = grupo.length;
                    const desc = grupo[0].descripcion;
                    const valor = Math.abs(grupo[0].valor);
                    html += `<div class="cuota-grupo"><span class="cuota-desc">${desc}</span><span class="cuota-valor">${formatPesos(valor)} × ${totalCuotas} cuotas</span></div>`;
                });
                html += `</div>`;
            }

            html += `<div class="detalle-resumen"><h4 class="detalle-subtitle">Resumen</h4><div class="resumen-grid">`;
            html += `<div class="resumen-item positivo"><span class="resumen-label">Ingresos</span><span class="resumen-valor">${d.total_ingresos_fmt}</span><span class="resumen-count">${d.num_ingresos} transacciones</span></div>`;
            html += `<div class="resumen-item negativo"><span class="resumen-label">Egresos</span><span class="resumen-valor">${d.total_gastos_fmt}</span><span class="resumen-count">${d.num_gastos} transacciones</span></div>`;
            html += `</div></div>`;

            html += `<div class="detalle-txs"><h4 class="detalle-subtitle">Transacciones</h4>`;
            const todas = [...d.transacciones];
            todas.sort((a, b) => (b.fecha_date || '').localeCompare(a.fecha_date || ''));
            todas.forEach(t => {
                const icono = t.es_ingreso ? '💰' : '💸';
                const cuotaTag = t.es_cuota ? '<span class="tx-cuota-badge">🔄 Cuota</span>' : '';
                html += `<div class="detalle-tx"><span class="tx-icono">${icono}</span><div class="tx-body"><span class="tx-desc">${t.descripcion || '—'} ${cuotaTag}</span><span class="tx-fecha">${t.fecha || ''}</span></div><span class="tx-valor ${t.es_ingreso ? 'positivo' : 'negativo'}">${t.valor_fmt}</span></div>`;
            });
            html += `</div>`;

            document.getElementById('detalle-body').innerHTML = html;
        })
        .catch(() => {
            document.getElementById('detalle-body').innerHTML = '<div class="detalle-loading">Error cargando detalle</div>';
        });
}

function cerrarDetalle(e) {
    if (e && e.target && e.target !== e.currentTarget) return;
    document.getElementById('detalle-modal').style.display = 'none';
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        const m = document.getElementById('detalle-modal');
        if (m && m.style.display !== 'none') m.style.display = 'none';
    }
});
