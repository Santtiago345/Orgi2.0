function switchTab(tab) {
    document.querySelectorAll('.ctab').forEach(b => b.classList.toggle('active', b.dataset.tab === tab));
    document.querySelectorAll('.tab-content').forEach(d => d.style.display = 'none');
    document.getElementById(`tab-${tab}`).style.display = 'block';
}

function fmt(val, decimals = 0) {
    if (val == null) return '—';
    const abs = Math.abs(val);
    const s = abs.toLocaleString('es-CO', { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
    return val < 0 ? `-$${s}` : `$${s}`;
}

function utilizacionBar(pct) {
    const cls = pct > 80 ? 'bar-danger' : pct > 50 ? 'bar-warning' : 'bar-safe';
    return `<div class="uso-bar-wrap"><div class="uso-bar ${cls}" style="width:${Math.min(pct,100)}%"></div></div>`;
}

document.addEventListener('DOMContentLoaded', () => {
    cargarTarjetas();
    cargarPrestamos();
});

function cargarTarjetas() {
    fetch('/api/perfil-crediticio')
        .then(r => r.json())
        .then(data => {
            const container = document.getElementById('tarjetas-content');
            if (!data.tarjetas || data.tarjetas.length === 0) {
                container.innerHTML = '<div class="creditos-loading">Sin información de tarjetas de crédito</div>';
                return;
            }

            const nombres = { nu: 'Nu Bank', rappicard: 'RappiCard / Davivienda' };
            const iconos  = { nu: '💚', rappicard: '💛' };

            let html = '';
            data.tarjetas.forEach(t => {
                const actualizado = t.extracto_actualizado;
                const estadoBadge = actualizado
                    ? `<span class="badge-ok">✓ Al día (${t.periodo_extracto})</span>`
                    : `<span class="badge-warn">⚠ Último extracto: ${t.periodo_extracto}</span>`;

                html += `
                <div class="tc-card ${t.utilizacion > 80 ? 'tc-danger' : ''}">
                    <div class="tc-card-header">
                        <span class="tc-card-icono">${iconos[t.fuente] || '💳'}</span>
                        <div class="tc-card-info">
                            <span class="tc-card-nombre">${nombres[t.fuente] || t.fuente}</span>
                            <span class="tc-card-sub">${t.num_extractos} extractos · ${estadoBadge}</span>
                        </div>
                    </div>
                    <div class="tc-uso-row">
                        <span class="tc-uso-lbl">Utilización del cupo: <strong class="${t.utilizacion > 80 ? 'danger' : t.utilizacion > 50 ? 'warning' : 'safe'}">${t.utilizacion}%</strong></span>
                        ${utilizacionBar(t.utilizacion)}
                    </div>
                    <div class="tc-card-grid">
                        <div class="tc-card-item">
                            <span class="tc-card-label">Deuda Actual</span>
                            <span class="tc-card-valor highlight">${t.deuda_total_fmt}</span>
                        </div>
                        <div class="tc-card-item">
                            <span class="tc-card-label">Pago Mínimo</span>
                            <span class="tc-card-valor">${t.pago_minimo_total_fmt}</span>
                        </div>
                        <div class="tc-card-item">
                            <span class="tc-card-label">Cupo Total</span>
                            <span class="tc-card-valor">${t.cupo_total_fmt}</span>
                        </div>
                        <div class="tc-card-item">
                            <span class="tc-card-label">Fecha Corte</span>
                            <span class="tc-card-valor sm">${t.fecha_corte}</span>
                        </div>
                        <div class="tc-card-item">
                            <span class="tc-card-label">Fecha Pago</span>
                            <span class="tc-card-valor sm">${t.fecha_pago}</span>
                        </div>
                        <div class="tc-card-item">
                            <span class="tc-card-label">Cupo Libre</span>
                            <span class="tc-card-valor safe">${fmt(Math.max(0, (t.cupo_total || 0) - (t.deuda_total || 0)))}</span>
                        </div>
                    </div>
                </div>`;
            });

            const fuentes = [...new Set(data.extractos.map(e => e.fuente))];
            fuentes.forEach(fuente => {
                const exts = data.extractos.filter(e => e.fuente === fuente);
                html += `<h3 class="creditos-subtitle">${iconos[fuente] || '💳'} Historial ${nombres[fuente] || fuente}</h3>
                <div class="tc-table-wrap">
                <table class="tc-table">
                    <thead><tr>
                        <th>Periodo</th><th>Total Pagar</th><th>Pago Mín.</th>
                        <th>Cupo</th><th>Saldo Ant.</th><th>Saldo Act.</th>
                        <th>Cargos</th><th>Abonos</th><th>F. Corte</th><th>F. Pago</th>
                        <th>Interés</th><th>Tasa M.</th>
                    </tr></thead><tbody>`;
                exts.forEach(e => {
                    const intBadge = e.interes_corriente ? `$${e.interes_corriente.toLocaleString('es-CO')}` : '—';
                    const tasaBadge = e.tasa_mensual ? `${e.tasa_mensual.toFixed(2)}%` : '—';
                    html += `<tr>
                        <td class="td-periodo">${e.periodo || `${e.anio}-${String(e.mes).padStart(2,'0')}`}</td>
                        <td class="td-highlight">${fmt(e.total_pagar)}</td>
                        <td>${fmt(e.pago_minimo)}</td>
                        <td>${fmt(e.cupo_total)}</td>
                        <td>${fmt(e.saldo_anterior)}</td>
                        <td>${fmt(e.saldo_actual)}</td>
                        <td>${fmt(e.total_cargos)}</td>
                        <td class="td-abono">${fmt(e.total_abonos)}</td>
                        <td class="td-fecha">${e.fecha_corte || '—'}</td>
                        <td class="td-fecha">${e.fecha_pago || '—'}</td>
                        <td class="td-interes">${intBadge}</td>
                        <td class="td-tasa">${tasaBadge}</td>
                    </tr>`;
                });
                html += `</tbody></table></div>`;
            });

            container.innerHTML = html;
        })
        .catch(() => {
            document.getElementById('tarjetas-content').innerHTML =
                '<div class="creditos-loading">Error cargando tarjetas</div>';
        });
}

function cargarPrestamos() {
    fetch('/api/prestamos-nequi')
        .then(r => r.json())
        .then(prestamos => {
            const container = document.getElementById('prestamos-content');
            if (!prestamos || prestamos.length === 0) {
                container.innerHTML = '<div class="creditos-loading">No se encontraron préstamos de Nequi</div>';
                return;
            }

            let html = `<p class="prestamos-intro">Se encontraron <strong>${prestamos.length}</strong> préstamos de Nequi en tu historial.</p>`;

            prestamos.forEach((p, i) => {
                const estadoCls = p.estado === 'pagado' ? 'badge-ok' : 'badge-warn';
                const estadoTxt = p.estado === 'pagado' ? '✓ Pagado' : '⏳ Activo';

                html += `
                <div class="prestamo-card ${p.estado === 'pagado' ? 'prestamo-pagado' : 'prestamo-activo'}">
                    <div class="prestamo-header">
                        <div class="prestamo-num">Préstamo #${prestamos.length - i}</div>
                        <span class="${estadoCls}">${estadoTxt}</span>
                    </div>
                    <div class="prestamo-fecha">📅 Desembolsado: <strong>${p.fecha_desembolso}</strong></div>
                    <div class="prestamo-grid">
                        <div class="prestamo-item">
                            <span class="tc-card-label">Monto Prestado</span>
                            <span class="tc-card-valor highlight">${p.monto_prestado_fmt}</span>
                        </div>
                        <div class="prestamo-item">
                            <span class="tc-card-label">Total Pagado</span>
                            <span class="tc-card-valor safe">${p.total_pagado_fmt}</span>
                        </div>
                        <div class="prestamo-item">
                            <span class="tc-card-label">Saldo Pendiente</span>
                            <span class="tc-card-valor ${p.saldo_pendiente > 0 ? 'danger' : 'safe'}">${p.saldo_pendiente_fmt}</span>
                        </div>
                    </div>
                    <div class="prestamo-barra-wrap">
                        <div class="prestamo-barra">
                            <div class="prestamo-barra-fill" style="width:${Math.min(p.porcentaje_pagado, 100)}%"></div>
                        </div>
                        <span class="prestamo-pct">${p.porcentaje_pagado}% pagado</span>
                    </div>`;

                if (p.pagos && p.pagos.length > 0) {
                    html += `
                    <details class="prestamo-pagos">
                        <summary>Ver ${p.pagos.length} pago(s) realizados</summary>
                        <table class="pagos-table">
                            <thead><tr><th>Fecha</th><th>Descripción</th><th>Valor</th></tr></thead>
                            <tbody>`;
                    p.pagos.forEach(pg => {
                        html += `<tr>
                            <td>${pg.fecha}</td>
                            <td>${pg.descripcion}</td>
                            <td class="td-highlight">${pg.valor_fmt}</td>
                        </tr>`;
                    });
                    html += `</tbody></table></details>`;
                }
                html += `</div>`;
            });

            container.innerHTML = html;
        })
        .catch(() => {
            document.getElementById('prestamos-content').innerHTML =
                '<div class="creditos-loading">Error cargando préstamos</div>';
        });
}
