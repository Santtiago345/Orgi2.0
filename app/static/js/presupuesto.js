let presupuestosData = [];
let editingPresupuesto = null;

document.addEventListener('DOMContentLoaded', () => {
    const anioSel = document.getElementById('presu-anio');
    const hoy = new Date();
    for (let a = hoy.getFullYear(); a >= hoy.getFullYear() - 3; a--) {
        const opt = document.createElement('option');
        opt.value = a; opt.textContent = a;
        if (a === hoy.getFullYear()) opt.selected = true;
        anioSel.appendChild(opt);
    }
    document.getElementById('presu-mes').value = hoy.getMonth() + 1;
    cargarPresupuesto();
});

function cargarPresupuesto() {
    const mes = document.getElementById('presu-mes').value;
    const anio = document.getElementById('presu-anio').value;
    fetch(`/api/presupuestos/resumen?mes=${mes}&anio=${anio}`)
        .then(r => r.json())
        .then(data => {
            presupuestosData = data;
            renderPresupuesto(data);
        })
        .catch(() => {
            document.getElementById('presu-grid').innerHTML = '<div class="presu-loading">Error cargando</div>';
        });
}

function renderPresupuesto(data) {
    const grid = document.getElementById('presu-grid');
    if (data.length === 0) {
        grid.innerHTML = '<div class="presu-loading">Sin presupuestos definidos. Presiona + para añadir uno.</div>';
        return;
    }
    grid.innerHTML = data.map(d => {
        const estadoCls = d.estado === 'excedido' ? 'presu-excedido' : d.estado === 'advertencia' ? 'presu-advertencia' : 'presu-ok';
        const barCls = d.estado === 'excedido' ? 'bar-danger' : d.estado === 'advertencia' ? 'bar-warning' : 'bar-safe';
        const icono = d.icono || '📌';
        const color = d.color || '#C9CBCF';
        return `<div class="presu-card ${estadoCls}">
            <div class="presu-card-header">
                <span class="presu-card-icono" style="background:${color}">${icono}</span>
                <div class="presu-card-info">
                    <span class="presu-card-nombre">${d.categoria}</span>
                    <span class="presu-card-sub">${d.gastado_fmt} de ${d.monto_fmt}</span>
                </div>
                <span class="presu-card-pct ${barCls}">${d.porcentaje}%</span>
                <button class="presu-card-del" onclick="eliminarPresupuesto(${d.id})" title="Eliminar">🗑️</button>
            </div>
            <div class="presu-bar-wrap">
                <div class="presu-bar ${barCls}" style="width:${Math.min(d.porcentaje, 100)}%"></div>
            </div>
            <div class="presu-card-footer">
                <span class="presu-restante ${d.porcentaje <= 100 ? 'ok' : 'excedido'}">
                    ${d.porcentaje <= 100 ? `Restan ${fmt((d.monto - d.gastado))}` : `Excedido en ${fmt((d.gastado - d.monto))}`}
                </span>
            </div>
        </div>`;
    }).join('');
}

function fmt(val) {
    return '$' + Math.abs(val).toLocaleString('es-CO');
}

function abrirModalPresupuesto(cat) {
    editingPresupuesto = null;
    document.getElementById('modal-presu-titulo').textContent = 'Añadir Presupuesto';
    document.getElementById('form-presu-id').value = '';
    document.getElementById('form-presu-monto').value = '';
    document.getElementById('form-presu-categoria').value = '';
    document.querySelectorAll('#presu-categoria-iconos .cat-icono').forEach(b => b.classList.remove('selected'));
    if (cat) {
        const btn = document.querySelector(`#presu-categoria-iconos .cat-icono[data-cat="${cat}"]`);
        if (btn) { btn.classList.add('selected'); document.getElementById('form-presu-categoria').value = cat; }
    }
    document.getElementById('modal-presupuesto').style.display = 'flex';
}

function cerrarModalPresupuesto(e) {
    if (e && e.target && e.target !== e.currentTarget) return;
    document.getElementById('modal-presupuesto').style.display = 'none';
}

function seleccionarCatPresu(btn) {
    document.querySelectorAll('#presu-categoria-iconos .cat-icono').forEach(b => b.classList.remove('selected'));
    btn.classList.add('selected');
    document.getElementById('form-presu-categoria').value = btn.dataset.cat;
}

function guardarPresupuesto(e) {
    e.preventDefault();
    const categoria = document.getElementById('form-presu-categoria').value;
    const monto = parseFloat(document.getElementById('form-presu-monto').value);
    const mes = parseInt(document.getElementById('presu-mes').value);
    const anio = parseInt(document.getElementById('presu-anio').value);
    if (!categoria) { alert('Selecciona una categoría'); return; }
    if (!monto || monto <= 0) { alert('Ingresa un monto válido'); return; }
    fetch('/api/presupuestos', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({categoria, monto, mes, anio})
    })
    .then(r => r.json())
    .then(res => {
        if (res.ok) {
            cerrarModalPresupuesto();
            cargarPresupuesto();
        } else {
            alert('Error: ' + (res.error || 'Desconocido'));
        }
    });
}

function eliminarPresupuesto(id) {
    if (!confirm('Eliminar este presupuesto?')) return;
    fetch('/api/presupuestos/' + id, {method: 'DELETE'})
        .then(r => r.json())
        .then(res => {
            if (res.ok) cargarPresupuesto();
            else alert('Error al eliminar');
        });
}

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const m = document.getElementById('modal-presupuesto');
        if (m && m.style.display !== 'none') m.style.display = 'none';
    }
});
