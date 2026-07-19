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
        mostrarError('Solo se aceptan archivos PDF');
        return;
    }
    document.getElementById('upload-card').style.display = 'none';
    document.getElementById('upload-result').style.display = 'none';
    document.getElementById('upload-progress').style.display = 'block';
    document.getElementById('upload-status').textContent = 'Procesando extracto...';
    document.getElementById('upload-substatus').textContent = file.name;

    const formData = new FormData();
    formData.append('pdf', file);
    fetch('/api/upload-pdf', { method: 'POST', body: formData })
        .then(r => r.json().then(data => ({status: r.status, data})))
        .then(({status, data}) => {
            document.getElementById('upload-progress').style.display = 'none';
            if (status === 409) {
                document.getElementById('upload-card').style.display = 'block';
                const existente = data.existente || {};
                const nombresBanco = {nequi: 'Nequi', nu: 'Nu Bank', rappicard: 'RappiCard', dale: 'Dale', daviplata: 'Daviplata'};
                const resultDiv = document.getElementById('upload-result');
                resultDiv.innerHTML = `<div class="result-duplicate"><span class="result-icon">⚠️</span><div class="result-info"><strong>Extracto ya procesado</strong><p>Banco: ${nombresBanco[existente.fuente] || existente.fuente} | Período: ${existente.periodo || '—'} | ${existente.num_transacciones || 0} transacciones</p><small>Archivo: ${existente.archivo || '—'}</small></div></div>`;
                resultDiv.style.display = 'block';
                return;
            }
            if (status !== 200) {
                document.getElementById('upload-card').style.display = 'block';
                mostrarError(data.error || 'Error desconocido al procesar');
                if (data.logs && data.logs.length > 0) mostrarLogs(data.logs);
                return;
            }
            const resultDiv = document.getElementById('upload-result');
            if (data.success) {
                const tipoLabel = data.tipo === 'tarjeta_credito' ? 'Tarjeta de Crédito' : 'Cuenta Corriente';
                let resumenHtml = '';
                if (data.logs && data.logs.length > 0) {
                    const lineas = filtrarLogs(data.logs);
                    if (lineas.length > 0) {
                        resumenHtml = `<div class="upload-resumen">${lineas.map(l => `<div class="upload-resumen-linea">${l}</div>`).join('')}</div>`;
                    }
                }
                resultDiv.innerHTML = `<div class="result-ok"><span class="result-icon">✅</span><div class="result-info"><strong>${data.archivo_original}</strong><p>Banco: ${data.banco} | Período: ${data.periodo} | Tipo: ${tipoLabel}</p></div></div>${resumenHtml}`;
                resultDiv.style.display = 'block';
                cargarExtractos();
                document.getElementById('upload-card').style.display = 'block';
            } else {
                document.getElementById('upload-card').style.display = 'block';
                const resultDiv = document.getElementById('upload-result');
                resultDiv.innerHTML = `<div class="result-error"><span class="result-icon">❌</span><div class="result-info"><strong>Error procesando el PDF</strong><p>${data.error || 'Error desconocido'}</p></div></div>`;
                if (data.logs && data.logs.length > 0) mostrarLogs(data.logs);
                resultDiv.style.display = 'block';
                document.getElementById('upload-card').style.display = 'block';
            }
        })
        .catch(err => {
            document.getElementById('upload-progress').style.display = 'none';
            document.getElementById('upload-card').style.display = 'block';
            mostrarError('Error de conexión');
        });
}

function filtrarLogs(logs) {
    const keywords = ['[OK]', '[ERROR]', '[SKIP]', 'RESULTADO', 'Procesando', 'Procesados', 'completado', 'fallo', 'exitosos', 'fallidos'];
    return logs.filter(l => {
        const clean = l.trim();
        if (!clean) return false;
        if (clean.startsWith('=') || clean.startsWith('-')) return false;
        return keywords.some(k => clean.includes(k));
    });
}

function mostrarError(msg) {
    const resultDiv = document.getElementById('upload-result');
    resultDiv.innerHTML = `<div class="result-error"><span class="result-icon">❌</span><div class="result-info"><strong>Error</strong><p>${msg}</p></div></div>`;
    resultDiv.style.display = 'block';
}

function mostrarLogs(logs) {
    const lineas = filtrarLogs(logs);
    if (lineas.length === 0) return;
    const resultDiv = document.getElementById('upload-result');
    const existing = resultDiv.querySelector('.upload-resumen');
    if (existing) existing.remove();
    resultDiv.insertAdjacentHTML('beforeend', `<div class="upload-resumen">${lineas.map(l => `<div class="upload-resumen-linea">${l}</div>`).join('')}</div>`);
}

function cargarExtractos() {
    const container = document.getElementById('extractos-list');
    container.innerHTML = '<div class="extractos-loading">Cargando extractos...</div>';
    fetch('/api/extractos')
        .then(r => r.json())
        .then(data => {
            extractosData = data;
            if (data.length === 0) { container.innerHTML = '<div class="extractos-loading">No hay extractos cargados</div>'; return; }

            const cuentas = data.filter(e => e.tipo !== 'tarjeta_credito');
            const tarjetas = data.filter(e => e.tipo === 'tarjeta_credito');
            const ordenCuentas = ['nequi', 'dale', 'daviplata'];
            const ordenTarjetas = ['nu', 'rappicard'];
            const nombres = {nequi: 'Nequi', nu: 'Nu Bank', rappicard: 'RappiCard', dale: 'Dale', daviplata: 'Daviplata'};

            function buildSection(titulo, icono, lista, orden) {
                if (lista.length === 0) return '';
                const grupos = {};
                lista.forEach(e => { const key = e.fuente || 'desconocido'; if (!grupos[key]) grupos[key] = []; grupos[key].push(e); });
                let html = `<div class="extractos-section"><h2 class="section-title">${icono} ${titulo}</h2>`;
                orden.forEach(banco => {
                    if (!grupos[banco]) return;
                    html += `<div class="banco-grupo"><h3 class="banco-titulo">${nombres[banco] || banco} <span class="banco-count">${grupos[banco].length}</span></h3><div class="banco-lista">`;
                    grupos[banco].forEach(e => {
                        const tipoIcono = e.tipo === 'tarjeta_credito' ? '💳' : '🏦';
                        html += `<div class="extracto-item" onclick="abrirDetalle(${e.id})"><span class="extracto-icono">${tipoIcono}</span><div class="extracto-info"><span class="extracto-periodo">${e.periodo || '—'}</span><span class="extracto-titular">${e.titular || ''}</span></div><span class="extracto-txs">${e.num_transacciones || 0} tx</span></div>`;
                    });
                    html += '</div></div>';
                });
                html += '</div>';
                return html;
            }

            let html = '';
            html += buildSection('Cuentas', '🏦', cuentas, ordenCuentas);
            html += buildSection('Tarjetas de Crédito', '💳', tarjetas, ordenTarjetas);
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
