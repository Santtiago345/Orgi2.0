let tendenciaChart = null;

document.addEventListener('DOMContentLoaded', () => {
    const hoy = new Date();
    const anio = hoy.getFullYear();
    [document.getElementById('comp-anio'), document.getElementById('res-anio')].forEach(sel => {
        for (let a = anio; a >= anio - 3; a--) {
            const opt = document.createElement('option');
            opt.value = a; opt.textContent = a;
            if (a === anio) opt.selected = true;
            sel.appendChild(opt);
        }
    });
    cargarTendencia();
    cargarComparativa();
    cargarTop();
    cargarResumen();
});

function switchRTab(tab) {
    document.querySelectorAll('.rtab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.rtab-content').forEach(d => d.style.display = 'none');
    document.getElementById('rtab-' + tab).style.display = 'block';
    if (tab === 'tendencia' && tendenciaChart) {
        setTimeout(() => tendenciaChart.resize(), 100);
    }
}

function cargarTendencia() {
    fetch('/api/reportes/tendencia?meses=12')
        .then(r => r.json())
        .then(data => {
            renderTendencia(data);
        });
}

function renderTendencia(data) {
    const ctx = document.getElementById('chart-tendencia').getContext('2d');
    if (tendenciaChart) tendenciaChart.destroy();

    const labels = data.map(d => {
        const meses = ['Ene','Feb','Mar','Abr','May','Jun','Jul','Ago','Sep','Oct','Nov','Dic'];
        return meses[parseInt(d.mes)-1] + ' ' + d.anio;
    });
    const ingresos = data.map(d => d.ingresos);
    const gastos = data.map(d => d.gastos);

    tendenciaChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels,
            datasets: [
                { label: 'Ingresos', data: ingresos, borderColor: '#16a34a', backgroundColor: 'rgba(22,163,74,0.1)', fill: true, tension: 0.3, pointRadius: 4 },
                { label: 'Gastos', data: gastos, borderColor: '#dc2626', backgroundColor: 'rgba(220,38,38,0.1)', fill: true, tension: 0.3, pointRadius: 4 },
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { position: 'top', labels: { boxWidth: 12, padding: 12 } },
                tooltip: {
                    callbacks: {
                        label: function(ctx) { return ' ' + ctx.dataset.label + ': $' + Number(ctx.raw).toLocaleString('es-CO'); }
                    }
                }
            },
            scales: {
                y: {
                    beginAtZero: true,
                    ticks: { callback: function(v) { return '$' + Number(v).toLocaleString('es-CO'); } }
                }
            }
        }
    });
}

function cargarComparativa() {
    const anio = document.getElementById('comp-anio').value;
    fetch('/api/reportes/comparativa?anio=' + anio)
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('comparativa-content');
            if (data.length === 0) {
                container.innerHTML = '<div class="reporte-loading">Sin datos</div>';
                return;
            }
            container.innerHTML = `<div class="comp-table-wrap"><table class="comp-table">
                <thead><tr><th>Categoría</th><th>Año Anterior</th><th>Año Actual</th><th>Diferencia</th><th>Cambio</th></tr></thead>
                <tbody>${data.map(d => {
                    const diffCls = d.diferencia > 0 ? 'negativo' : d.diferencia < 0 ? 'positivo' : '';
                    const icono = d.icono || '';
                    return `<tr>
                        <td>${icono} ${d.categoria}</td>
                        <td>${d.anterior_fmt}</td>
                        <td>${d.actual_fmt}</td>
                        <td class="${diffCls}">${d.diferencia_fmt}</td>
                        <td class="${diffCls}">${d.porcentaje_cambio > 0 ? '+' : ''}${d.porcentaje_cambio}%</td>
                    </tr>`;
                }).join('')}</tbody></table></div>`;
        });
}

function cargarTop() {
    const desde = document.getElementById('top-desde').value;
    const hasta = document.getElementById('top-hasta').value;
    const limite = document.getElementById('top-limite').value;
    let params = 'limite=' + limite;
    if (desde) params += '&desde=' + desde;
    if (hasta) params += '&hasta=' + hasta;

    fetch('/api/reportes/top-gastos?' + params)
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('top-content');
            if (data.length === 0) {
                container.innerHTML = '<div class="reporte-loading">Sin gastos en el período</div>';
                return;
            }
            const total = data.reduce((s, d) => s + d.valor_abs, 0);
            container.innerHTML = `<p class="top-total">Total: <strong>${fmt(total)}</strong> · ${data.length} gastos</p>
                <div class="top-lista">${data.map((d, i) => {
                    const fecha = d.fecha_date ? new Date(d.fecha_date + 'T12:00:00').toLocaleDateString('es-CO', { day: 'numeric', month: 'short' }) : d.fecha;
                    const icono = d.icono || '📌';
                    return `<div class="top-item">
                        <span class="top-num">#${i+1}</span>
                        <span class="top-icono" style="background:${d.color || '#C9CBCF'}">${icono}</span>
                        <div class="top-info">
                            <span class="top-desc">${d.descripcion || '—'}</span>
                            <span class="top-meta">${fecha} · ${d.categoria}</span>
                        </div>
                        <span class="top-valor">${d.valor_fmt}</span>
                    </div>`;
                }).join('')}</div>`;
        });
}

function cargarResumen() {
    const anio = document.getElementById('res-anio').value;
    fetch('/api/reportes/resumen-anual?anio=' + anio)
        .then(r => r.json())
        .then(d => {
            const container = document.getElementById('resumen-content');
            container.innerHTML = `<div class="resumen-grid">
                <div class="resumen-card res-ingresos">
                    <span class="res-icon">💰</span>
                    <span class="res-label">Total Ingresos</span>
                    <span class="res-valor">${d.total_ingresos_fmt}</span>
                </div>
                <div class="resumen-card res-gastos">
                    <span class="res-icon">💸</span>
                    <span class="res-label">Total Gastos</span>
                    <span class="res-valor">${d.total_gastos_fmt}</span>
                </div>
                <div class="resumen-card res-balance ${d.balance >= 0 ? 'positivo' : 'negativo'}">
                    <span class="res-icon">⚖️</span>
                    <span class="res-label">Balance</span>
                    <span class="res-valor">${d.balance_fmt}</span>
                </div>
                <div class="resumen-card res-promedio">
                    <span class="res-icon">📊</span>
                    <span class="res-label">Gasto Promedio / Mes</span>
                    <span class="res-valor">${d.gasto_promedio_mensual_fmt}</span>
                </div>
                <div class="resumen-card res-promedio-ing">
                    <span class="res-icon">📈</span>
                    <span class="res-label">Ingreso Promedio / Mes</span>
                    <span class="res-valor">${d.ingreso_promedio_mensual_fmt}</span>
                </div>
                <div class="resumen-card res-tx">
                    <span class="res-icon">📝</span>
                    <span class="res-label">Transacciones</span>
                    <span class="res-valor">${Number(d.num_transacciones).toLocaleString('es-CO')}</span>
                </div>
            </div>`;
        });
}

function fmt(val) {
    return '$' + Math.abs(val).toLocaleString('es-CO');
}
