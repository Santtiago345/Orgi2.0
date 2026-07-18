const estado = {
    tipo: 'gastos',
    periodo: 'dia',
    desde: null,
    hasta: null,
    chart: null,
    txViewerData: [],
    txViewerOrden: 'fecha',
    txViewerDesc: true,
    etiquetas: [],
};

function cambiarTipo(tipo) {
    estado.tipo = tipo;
    document.querySelectorAll('.tipo-btn').forEach(b => b.classList.toggle('active', b.dataset.tipo === tipo));
    document.getElementById('btn-agregar').title = tipo === 'gastos' ? 'Agregar gasto' : 'Agregar ingreso';
    cerrarTxViewer();
    cargarDatos();
}

function cambiarPeriodo(periodo) {
    estado.periodo = periodo;
    document.querySelectorAll('.periodo-btn').forEach(b => b.classList.toggle('active', b.dataset.periodo === periodo));
    const perso = periodo === 'personalizado';
    document.getElementById('fechas-perso').style.display = perso ? 'flex' : 'none';
    if (perso) {
        const hoy = new Date();
        document.getElementById('input-hasta').value = hoy.toISOString().split('T')[0];
        const inicio = new Date(hoy.getFullYear(), hoy.getMonth(), 1);
        document.getElementById('input-desde').value = inicio.toISOString().split('T')[0];
    }
    cerrarTxViewer();
    cargarDatos();
}

function formatearFecha(iso) {
    const d = new Date(iso + 'T12:00:00');
    return d.toLocaleDateString('es-CO', { day: 'numeric', month: 'short', year: 'numeric' });
}

function mostrarFechas(desde, hasta) {
    document.getElementById('fecha-desde').textContent = formatearFecha(desde);
    document.getElementById('fecha-hasta').textContent = formatearFecha(hasta);
}

function navegar(dir) {
    if (!estado.desde || !estado.hasta) return;
    const params = new URLSearchParams({
        tipo: estado.tipo, periodo: estado.periodo,
        desde: estado.desde, hasta: estado.hasta, dir: dir
    });
    fetch(`/api/navegar?${params}`)
        .then(r => { if (!r.ok) throw new Error('Error navegando'); return r.json(); })
        .then(data => {
            estado.desde = data.desde;
            estado.hasta = data.hasta;
            actualizarVista(data);
        })
        .catch(() => cargarDatos());
}

function irAHoy() {
    cerrarTxViewer();
    cargarDatos();
}

function esPeriodoActual() {
    if (!estado.desde) return true;
    const params = new URLSearchParams({
        tipo: estado.tipo, periodo: estado.periodo,
        desde: estado.desde, hasta: estado.hasta
    });
    fetch(`/api/resumen?${params}`)
        .then(r => r.json())
        .then(data => {
            document.getElementById('btn-hoy').style.display = data.es_actual ? 'none' : 'flex';
        });
}

function cargarDatos() {
    cerrarTxViewer();
    let params = `tipo=${estado.tipo}&periodo=${estado.periodo}`;
    if (estado.periodo === 'personalizado') {
        const d = document.getElementById('input-desde').value;
        const h = document.getElementById('input-hasta').value;
        if (!d || !h) {
            mostrarVacia();
            return;
        }
        params += `&desde=${d}&hasta=${h}`;
    }

    fetch(`/api/resumen?${params}`)
        .then(r => { if (!r.ok) throw new Error('Error en API'); return r.json(); })
        .then(data => {
            estado.desde = data.desde;
            estado.hasta = data.hasta;
            actualizarVista(data);
        })
        .catch(() => mostrarVacia());
}

function mostrarVacia() {
    const hoy = new Date();
    const iso = hoy.toISOString().split('T')[0];
    estado.desde = estado.hasta = iso;
    mostrarFechas(iso, iso);
    document.getElementById('tabla-items').innerHTML = '<div class="tabla-vacia">Sin transacciones en este período</div>';
    document.getElementById('btn-hoy').style.display = 'none';
    actualizarGrafico([]);
}

function actualizarVista(data) {
    mostrarFechas(data.desde, data.hasta);
    document.getElementById('btn-hoy').style.display = data.es_actual ? 'none' : 'flex';
    const container = document.getElementById('tabla-items');
    container.innerHTML = '';
    data.categorias.forEach(c => {
        const div = document.createElement('div');
        div.className = 'tabla-item';
        div.onclick = () => abrirTxViewer(c.categoria, data.transacciones);
        div.innerHTML = `
            <span class="tabla-item-icono" style="background:${c.color}">${c.icono}</span>
            <span class="tabla-item-cat">${c.categoria}</span>
            <span class="tabla-item-pct">${c.porcentaje}%</span>
            <span class="tabla-item-valor">$${Number(c.total).toLocaleString('es-CO')}</span>
        `;
        container.appendChild(div);
    });

    if (data.categorias.length === 0) {
        container.innerHTML = '<div class="tabla-vacia">Sin transacciones en este período</div>';
    }

    actualizarGrafico(data.categorias);
}

const centerTextPlugin = {
    id: 'centerText',
    beforeDraw(chart) {
        const { width, height, ctx } = chart;
        ctx.save();
        const centerX = width / 2;
        const centerY = height / 2;
        const total = chart.config.data.datasets[0].data.reduce((a, b) => a + b, 0);
        ctx.textAlign = 'center';
        ctx.textBaseline = 'middle';
        const fmt = total.toLocaleString('es-CO', {minimumFractionDigits: 0});
        ctx.font = 'bold 22px -apple-system, sans-serif';
        ctx.fillStyle = '#1D3557';
        ctx.fillText(`$${fmt}`, centerX, centerY + 4);
        ctx.font = '12px -apple-system, sans-serif';
        ctx.fillStyle = '#6B7280';
        ctx.fillText('Total', centerX, centerY - 18);
        ctx.restore();
    }
};

Chart.register(centerTextPlugin);

function actualizarGrafico(categorias) {
    const ctx = document.getElementById('chart-pastel').getContext('2d');
    if (estado.chart) estado.chart.destroy();

    const labels = categorias.map(c => c.categoria || 'Sin categoría');
    const values = categorias.map(c => c.total);
    const colors = categorias.map(c => c.color || '#C9CBCF');

    estado.chart = new Chart(ctx, {
        type: 'doughnut',
        data: {
            labels,
            datasets: [{
                data: values,
                backgroundColor: colors,
                borderWidth: 2,
                borderColor: '#fff'
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: true,
            cutout: '62%',
            plugins: {
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function(ctx) {
                            const val = Number(ctx.raw).toLocaleString('es-CO', {minimumFractionDigits: 0});
                            const total = ctx.dataset.data.reduce((a, b) => a + b, 0);
                            const pct = total > 0 ? (ctx.raw / total * 100).toFixed(1) : 0;
                            return ` ${ctx.label}: $${val} (${pct}%)`;
                        }
                    }
                }
            }
        },
        plugins: [centerTextPlugin]
    });
}

let txViewerData = [];
let txViewerCat = '';

function abrirTxViewer(categoria, todas) {
    txViewerCat = categoria;
    txViewerData = todas.filter(t => t.categoria === categoria);
    document.getElementById('tx-viewer-titulo').textContent = `${categoria} (${txViewerData.length} transacciones)`;
    document.getElementById('tx-viewer').style.display = 'block';
    const buscar = document.getElementById('tx-buscar');
    if (buscar) buscar.value = '';
    document.getElementById('tx-orden-campo').value = 'fecha';
    document.getElementById('tx-orden-dir').textContent = '↓ Desc';
    estado.txViewerDesc = true;
    document.querySelectorAll('.metodo-chk input').forEach(cb => cb.checked = true);
    renderTxViewer();
    document.getElementById('tx-viewer').scrollIntoView({ behavior: 'smooth' });
}

function cerrarTxViewer() {
    document.getElementById('tx-viewer').style.display = 'none';
    txViewerData = [];
    txViewerCat = '';
}

function resolverMetodo(t) {
    const entidad = (t.entidad || '').toLowerCase();
    const mp = (t.metodo_pago || '').toLowerCase();
    const cat = (t.categoria || '').toLowerCase();
    if (cat === 'sin cruzar') return 'sincruzar';
    if (entidad === 'nequi') return 'nequi';
    if (entidad === 'nu' || entidad === 'rappicard' || mp === 'tarjeta_credito' || mp === 'tarjeta') return 'tarjeta';
    if (entidad === 'manual' || entidad === 'myfinance') return 'manual';
    return 'otros';
}

function renderTxViewer() {
    const campo = document.getElementById('tx-orden-campo').value;
    const desc = estado.txViewerDesc;
    const buscar = (document.getElementById('tx-buscar').value || '').toLowerCase().trim();
    const seleccionados = Array.from(document.querySelectorAll('.metodo-chk input:checked')).map(cb => cb.value);

    let data = [...txViewerData];

    data = data.filter(t => seleccionados.includes(resolverMetodo(t)));

    if (buscar) {
        data = data.filter(t =>
            (t.descripcion || '').toLowerCase().includes(buscar) ||
            (t.categoria || '').toLowerCase().includes(buscar) ||
            (t.notas || '').toLowerCase().includes(buscar) ||
            (t.tags || []).some(tag => (tag.nombre || '').toLowerCase().includes(buscar))
        );
    }

    data.sort((a, b) => {
        let va = campo === 'valor' ? Math.abs(a.valor) : (a.fecha_date || '');
        let vb = campo === 'valor' ? Math.abs(b.valor) : (b.fecha_date || '');
        if (campo === 'fecha') { va = va || ''; vb = vb || ''; return desc ? vb.localeCompare(va) : va.localeCompare(vb); }
        return desc ? vb - va : va - vb;
    });

    const container = document.getElementById('tx-viewer-lista');
    if (data.length === 0) {
        container.innerHTML = '<div class="tx-viewer-vacia">Sin resultados</div>';
        return;
    }

    container.innerHTML = data.map(t => {
        const fecha = t.fecha_date ? new Date(t.fecha_date + 'T12:00:00').toLocaleDateString('es-CO', { day: 'numeric', month: 'short' }) : t.fecha;
        const val = Number(t.valor).toLocaleString('es-CO', {minimumFractionDigits: 0});
        const notas = t.notas ? `<div class="tx-nota">📝 ${t.notas}</div>` : '';
        const metodoIcon = {efectivo: '💵', tarjeta_credito: '💳', transferencia: '🏦'}[t.metodo_pago] || '';
        let cuotaBadge = '';
        if (t.es_cuota && t.cuota_info) {
            cuotaBadge = `<span class="tx-cuota-badge">${t.cuota_info.cuota_actual}/${t.cuota_info.total_cuotas}</span>`;
        }
        const tags = (t.tags || []).map(tag => `<span class="tag-badge" style="background:${tag.color}20;color:${tag.color};border-color:${tag.color}">${tag.nombre}</span>`).join(' ');
        return `
            <div class="tx-item" onclick="abrirDetalleTx(this, ${t.id})">
                <span class="tx-fecha">${fecha}</span>
                <span class="tx-metodo-icon">${metodoIcon}</span>
                <span class="tx-desc">${t.descripcion || '—'} ${cuotaBadge}</span>
                <span class="tx-valor">$${val}</span>
                ${notas}
                ${tags ? `<div class="tx-tags">${tags}</div>` : ''}
                <div class="tx-detail" id="tx-detail-${t.id}" style="display:none">
                    <div class="tx-detail-inner">
                        <div class="tx-detail-row"><span>Método</span><span>${metodoIcon} ${t.metodo_pago || '—'}</span></div>
                        <div class="tx-detail-row"><span>Entidad</span><span>${t.entidad || '—'}</span></div>
                        ${t.notas ? `<div class="tx-detail-row"><span>Notas</span><span>📝 ${t.notas}</span></div>` : ''}
                        ${t.es_cuota && t.cuota_info ? `
                        <div class="tx-detail-row"><span>Cuota</span><span>${t.cuota_info.cuota_actual} de ${t.cuota_info.total_cuotas}</span></div>
                        <div class="tx-detail-row"><span>Valor total</span><span>${t.valor_original_fmt ? '$' + Number(t.valor_original).toLocaleString('es-CO') : '—'}</span></div>
                        <div class="tx-detail-row"><span>Compra</span><span>${t.cuota_info.compra_desc}</span></div>
                        ` : ''}
                        ${tags ? `<div class="tx-detail-row"><span>Etiquetas</span><span>${tags}</span></div>` : ''}
                        <div class="tx-detail-actions">
                            <button class="btn-icon" onclick="event.stopPropagation();abrirAsignarEtiquetas(${t.id}, '${(t.descripcion||'').substring(0,20).replace(/'/g, "\\'")}')" title="Etiquetas">🏷️</button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

function filtrarTxViewer() { renderTxViewer(); }
function ordenarTxViewer() { renderTxViewer(); }

function abrirDetalleTx(el, txId) {
    const detail = document.getElementById('tx-detail-' + txId);
    if (!detail) return;
    document.querySelectorAll('.tx-detail').forEach(d => {
        if (d.id !== 'tx-detail-' + txId) d.style.display = 'none';
    });
    detail.style.display = detail.style.display === 'none' ? 'block' : 'none';
}

function abrirAsignarEtiquetas(txId, txDesc) {
    const detail = document.getElementById('tx-detail-' + txId);
    if (!detail) return;
    const actionsDiv = detail.querySelector('.tx-detail-actions');
    if (!actionsDiv) return;
    const existing = detail.querySelector('.tx-detail-tag-picker');
    if (existing) { existing.remove(); return; }
    const tags = (window.estado && window.estado.etiquetas) || [];
    if (tags.length === 0) {
        alert('No hay etiquetas. Ve a Categorías para crear una.');
        return;
    }
    const picker = document.createElement('div');
    picker.className = 'tx-detail-tag-picker';
    actionsDiv.appendChild(picker);
    fetch('/api/transacciones/' + txId + '/etiquetas')
        .then(r => r.json())
        .then(txTags => {
            const tagIds = txTags.map(t => t.id);
            picker.innerHTML = tags.map(e => {
                const assigned = tagIds.includes(e.id);
                return `<button class="tag-pick-btn ${assigned ? 'assigned' : ''}"
                    data-etq-id="${e.id}"
                    style="background:${e.color}20;border-color:${e.color}"
                    onclick="toggleTagTx(${txId}, ${e.id}, this)">
                    <span style="color:${e.color}">${e.nombre}</span>
                </button>`;
            }).join('');
        });
}

function toggleTagTx(txId, etqId, btn) {
    const assigned = btn.classList.contains('assigned');
    const method = assigned ? 'DELETE' : 'POST';
    const url = assigned
        ? '/api/transacciones/' + txId + '/etiquetas/' + etqId
        : '/api/transacciones/' + txId + '/etiquetas';
    const body = assigned ? undefined : JSON.stringify({etiqueta_id: etqId});
    fetch(url, {method, headers: {'Content-Type': 'application/json'}, body})
        .then(r => r.json())
        .then(() => btn.classList.toggle('assigned'));
}

function toggleOrdenDir() {
    estado.txViewerDesc = !estado.txViewerDesc;
    document.getElementById('tx-orden-dir').textContent = estado.txViewerDesc ? '↓ Desc' : '↑ Asc';
    renderTxViewer();
}

function abrirModal() {
    const tipo = estado.tipo === 'gastos' ? 'gasto' : 'ingreso';
    document.getElementById('form-tipo').value = tipo;
    document.querySelectorAll('.modal-tipo-btn').forEach(b => b.classList.toggle('active', b.dataset.mtipo === tipo));

    document.getElementById('form-desc').value = '';
    document.getElementById('form-valor').value = '';
    document.getElementById('form-notas').value = '';
    document.querySelectorAll('.metodo-btn').forEach(b => b.classList.remove('selected'));
    document.querySelector('.metodo-btn[data-metodo="transferencia"]').classList.add('selected');
    document.getElementById('form-metodo-pago').value = 'transferencia';

    seleccionarFecha(document.querySelector('.fecha-btn[data-fecha="hoy"]'), 'hoy');

    document.querySelectorAll('.cat-icono').forEach(b => b.classList.remove('selected'));
    document.querySelector('.cat-icono[data-cat="Varios"]')?.classList.add('selected');
    document.getElementById('form-categoria').value = 'Varios';

    document.getElementById('modal-overlay').style.display = 'flex';
}

function cerrarModal(e) {
    if (e && e.target && e.target !== e.currentTarget) return;
    document.getElementById('modal-overlay').style.display = 'none';
}

function cambiarModalTipo(tipo) {
    document.querySelectorAll('.modal-tipo-btn').forEach(b => b.classList.toggle('active', b.dataset.mtipo === tipo));
    document.getElementById('form-tipo').value = tipo;
}

function seleccionarCategoria(btn) {
    document.querySelectorAll('.cat-icono').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    document.getElementById('form-categoria').value = btn.dataset.cat;
}

function seleccionarMetodoPago(btn, metodo) {
    document.querySelectorAll('.metodo-btn').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    document.getElementById('form-metodo-pago').value = metodo;
}

function seleccionarFecha(btn, tipoFecha) {
    document.querySelectorAll('.fecha-btn:not(.fecha-cal-btn)').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');

    const input = document.getElementById('form-fecha');
    const hoy = new Date();
    let fecha;

    if (tipoFecha === 'hoy') {
        fecha = hoy;
    } else if (tipoFecha === 'ayer') {
        fecha = new Date(hoy);
        fecha.setDate(fecha.getDate() - 1);
    } else if (tipoFecha === 'ultima') {
        fetch('/api/ultima-fecha')
            .then(r => r.json())
            .then(data => {
                document.getElementById('form-fecha').value = data.fecha;
            });
        return;
    }

    input.value = fecha.toISOString().split('T')[0];
}

function fechaCalendario(valor) {
    document.querySelectorAll('.fecha-btn:not(.fecha-cal-btn)').forEach(b => b.classList.remove('selected'));
    document.getElementById('form-fecha').value = valor;
}

function guardarTransaccion(e) {
    e.preventDefault();
    const data = {
        fecha: document.getElementById('form-fecha').value,
        descripcion: document.getElementById('form-desc').value,
        valor: parseFloat(document.getElementById('form-valor').value),
        categoria: document.getElementById('form-categoria').value,
        tipo: document.getElementById('form-tipo').value,
        notas: document.getElementById('form-notas').value,
        metodo_pago: document.getElementById('form-metodo-pago').value,
    };

    fetch('/api/transacciones', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(r => r.json())
    .then(res => {
        if (res.ok) {
            cerrarModal();
            document.getElementById('form-transaccion').reset();
            if (res.balance_fmt) document.getElementById('balance-total').textContent = res.balance_fmt;
            cargarDatos();
        } else {
            alert('Error: ' + (res.error || 'Desconocido'));
        }
    });
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const modal = document.getElementById('modal-overlay');
        if (modal && modal.style.display !== 'none') { modal.style.display = 'none'; }
        const viewer = document.getElementById('tx-viewer');
        if (viewer && viewer.style.display !== 'none') { cerrarTxViewer(); }
    }
});

document.addEventListener('DOMContentLoaded', () => {
    document.getElementById('form-fecha').value = new Date().toISOString().split('T')[0];

    document.querySelectorAll('.periodo-btn').forEach(b => b.classList.toggle('active', b.dataset.periodo === estado.periodo));

    cargarDatos();

    fetch('/api/ultima-fecha').then(r => r.json()).then(data => {
        document.getElementById('btn-ultima-fecha').dataset.fechaValor = data.fecha;
    });

    fetch('/api/etiquetas').then(r => r.json()).then(data => {
        estado.etiquetas = data;
    });
});
