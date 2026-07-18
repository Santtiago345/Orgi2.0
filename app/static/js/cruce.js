let paginaActual = 0;
let txSeleccionadaId = null;
let txSeleccionadaEntidad = null;

document.addEventListener('DOMContentLoaded', () => {
    cargarEstadisticas();
    cargarCategorias();
    cargarSinCruzar();
});

function cargarEstadisticas() {
    fetch('/api/cruce/estadisticas')
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('cruce-estadisticas');
            let html = `
                <div class="cruce-stat-card info">
                    <span class="cruce-stat-valor">${fmt(data.sin_cruzar)}</span>
                    <span class="cruce-stat-label">Sin cruzar</span>
                </div>
                <div class="cruce-stat-card positivo">
                    <span class="cruce-stat-valor">${fmt(data.cruzadas)}</span>
                    <span class="cruce-stat-label">Cruzados</span>
                </div>
            `;
            data.por_entidad.forEach(e => {
                const nombres = {myfinance: 'MyF', nequi: 'Nequi', nu: 'Nu', rappicard: 'Rappi'};
                html += `
                    <div class="cruce-stat-card info">
                        <span class="cruce-stat-valor">${fmt(e.total)}</span>
                        <span class="cruce-stat-label">${nombres[e.entidad] || e.entidad}</span>
                    </div>
                `;
            });
            container.innerHTML = html;
        });
}

function cargarCategorias() {
    const select = document.getElementById('filtro-categoria');
    fetch('/api/cruce/estadisticas')
        .then(r => r.json())
        .then(data => {
            data.por_categoria.forEach(c => {
                const opt = document.createElement('option');
                opt.value = c.categoria;
                opt.textContent = `${c.categoria} (${c.total})`;
                select.appendChild(opt);
            });
        });
    const manualSelect = document.getElementById('sug-manual-cat');
    if (window.Orgi && window.Orgi.categorias) {
        window.Orgi.categorias.forEach(c => {
            const opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.icono + ' ' + c.id;
            manualSelect.appendChild(opt);
        });
    }
}

function cargarSinCruzar() {
    const entidad = document.getElementById('filtro-entidad').value;
    const categoria = document.getElementById('filtro-categoria').value;
    const limite = 50;
    const offset = paginaActual * limite;
    let params = `limite=${limite}&offset=${offset}`;
    if (entidad !== 'todas') params += '&entidad=' + entidad;
    if (categoria) params += '&categoria=' + categoria;

    const container = document.getElementById('cruce-lista');
    container.innerHTML = '<div class="cruce-loading">Cargando...</div>';

    fetch('/api/cruce/sin-cruzar?' + params)
        .then(r => r.json())
        .then(data => {
            document.getElementById('cruce-total').textContent = `${data.total} transacciones sin cruzar`;
            if (data.transacciones.length === 0) {
                container.innerHTML = '<div class="cruce-vacia">No hay transacciones sin cruzar</div>';
                document.getElementById('cruce-paginacion').innerHTML = '';
                return;
            }
            const totalPaginas = Math.ceil(data.total / limite);
            container.innerHTML = data.transacciones.map(t => {
                const entidadCls = 'badge-' + t.entidad;
                return `<div class="cruce-item">
                    <input type="checkbox" class="cruce-item-check" data-id="${t.id}" data-entidad="${t.entidad}">
                    <div class="cruce-item-info">
                        <span class="cruce-item-desc">${t.descripcion || '—'}</span>
                        <span class="cruce-item-meta">${t.fecha_date || t.fecha} <span class="badge-entidad ${entidadCls}">${t.entidad}</span> <span class="cruce-item-cat">${t.categoria || 'Sin categoría'}</span></span>
                        ${t.notas ? `<div class="cruce-item-notas">📝 ${t.notas}</div>` : ''}
                    </div>
                    <span class="cruce-item-valor">${t.valor_fmt}</span>
                    <button class="btn-cruzar sm" onclick="buscarMatch(${t.id})">🔍 Match</button>
                </div>`;
            }).join('');

            let pagHtml = '';
            if (paginaActual > 0) pagHtml += `<button class="page-btn" onclick="irPagina(${paginaActual - 1})">←</button>`;
            for (let i = Math.max(0, paginaActual - 2); i <= Math.min(totalPaginas - 1, paginaActual + 2); i++) {
                pagHtml += `<button class="page-btn ${i === paginaActual ? 'active' : ''}" onclick="irPagina(${i})">${i + 1}</button>`;
            }
            if (paginaActual < totalPaginas - 1) pagHtml += `<button class="page-btn" onclick="irPagina(${paginaActual + 1})">→</button>`;
            document.getElementById('cruce-paginacion').innerHTML = pagHtml;
        });
}

function irPagina(pag) {
    paginaActual = pag;
    cargarSinCruzar();
}

function buscarMatch(txId) {
    document.getElementById('modal-sugerencias').style.display = 'flex';
    document.getElementById('modal-sugerencia-lista').innerHTML = '<div class="cruce-loading">Buscando matches...</div>';
    document.getElementById('modal-sugerencia-tx').innerHTML = '';

    fetch('/api/cruce/sugerencias/' + txId)
        .then(r => r.json())
        .then(data => {
            txSeleccionadaId = txId;
            txSeleccionadaEntidad = data.length > 0 ? data[0].entidad : null;

            const txInfo = document.getElementById('modal-sugerencia-tx');
            fetch('/api/cruce/sin-cruzar?limite=1&offset=0')
                .then(r0 => r0.json())
                .then(allData => {
                });
            txInfo.innerHTML = `<div class="sug-tx-info-row"><span class="sug-tx-info-label">ID:</span><span class="sug-tx-info-valor">#${txId}</span></div>`;

            const lista = document.getElementById('modal-sugerencia-lista');
            if (data.length === 0) {
                lista.innerHTML = '<div class="cruce-vacia">No se encontraron sugerencias automáticas</div>';
                return;
            }
            lista.innerHTML = data.map(s => {
                const scoreCls = s.score >= 70 ? '' : s.score >= 40 ? 'medio' : 'bajo';
                return `<div class="sug-item">
                    <div class="sug-item-info">
                        <span class="sug-item-desc">${s.descripcion || '—'}</span>
                        <span class="sug-item-meta">${s.fecha_date} · ${s.entidad} · ${s.categoria || 'Sin categoría'}${s.notas ? '<br>📝 '+s.notas : ''}</span>
                    </div>
                    <span class="sug-item-valor">${s.valor_fmt}</span>
                    <span class="sug-item-score ${scoreCls}">${s.score}%</span>
                    <button class="btn-cruzar sm" onclick="confirmarCruce(${txId}, ${s.id})">Cruzar</button>
                </div>`;
            }).join('');
        });
}

function confirmarCruce(txBancaria, txMyfinance) {
    const body = {tx_id_bancaria: txBancaria, tx_id_myfinance: txMyfinance};
    fetch('/api/cruce/cruzar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                cerrarModalSugerencias(null);
                cargarEstadisticas();
                cargarSinCruzar();
            } else {
                alert('Error: ' + (data.error || 'No se pudo cruzar'));
            }
        });
}

function cruzarManual() {
    const manualCat = document.getElementById('sug-manual-cat').value;
    if (!txSeleccionadaId) return;

    const body = {tx_id_bancaria: txSeleccionadaId, tx_id_myfinance: txSeleccionadaId};
    fetch('/api/cruce/cruzar', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)})
        .then(r => r.json())
        .then(data => {
            if (data.ok) {
                cerrarModalSugerencias(null);
                cargarEstadisticas();
                cargarSinCruzar();
            } else {
                alert('Error: ' + (data.error || 'No se pudo cruzar'));
            }
        });
}

function cerrarModalSugerencias(e) {
    if (e && e.target && e.target !== e.currentTarget) return;
    document.getElementById('modal-sugerencias').style.display = 'none';
}

function fmt(val) {
    return Number(val).toLocaleString('es-CO');
}

document.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
        const m = document.getElementById('modal-sugerencias');
        if (m && m.style.display !== 'none') m.style.display = 'none';
    }
});