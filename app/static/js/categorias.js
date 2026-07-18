let categoriasData = [];
let catTxData = [];
let etiquetasData = [];

document.addEventListener('DOMContentLoaded', () => {
    cargarCategorias();
    cargarEtiquetas();
});

function cargarCategorias() {
    const grid = document.getElementById('cat-grid');
    grid.innerHTML = '<div class="cat-loading">Cargando categorias...</div>';
    fetch('/api/categorias')
        .then(r => r.json())
        .then(data => {
            categoriasData = data;
            if (data.length === 0) {
                grid.innerHTML = '<div class="cat-loading">No hay categorias</div>';
                return;
            }
            grid.innerHTML = data.map(c => {
                const icono = getIconoCat(c.categoria);
                const color = getColorCat(c.categoria);
                return `<div class="cat-card" onclick="abrirCatTx('${c.categoria}')" style="border-left: 4px solid ${color}">
                    <div class="cat-card-icono" style="background:${color}">${icono}</div>
                    <div class="cat-card-info">
                        <span class="cat-card-nombre">${c.categoria}</span>
                        <span class="cat-card-stats">${c.total_tx} tx &middot; $${Number(c.total_gastado).toLocaleString('es-CO')}</span>
                    </div>
                    <button class="cat-card-edit" onclick="event.stopPropagation();abrirEditarCategoria('${c.categoria}')" title="Editar categoria">⚙️</button>
                </div>`;
            }).join('');
        })
        .catch(() => grid.innerHTML = '<div class="cat-loading">Error cargando</div>');
}

function getIconoCat(cat) {
    const found = window.Orgi.categorias.find(c => c.id === cat);
    return found ? found.icono : '📌';
}

function getColorCat(cat) {
    const found = window.Orgi.categorias.find(c => c.id === cat);
    return found ? found.color : '#C9CBCF';
}

function abrirModalCategoria() {
    document.getElementById('modal-cat-titulo').textContent = 'Nueva Categoria';
    document.getElementById('form-cat-nombre-original').value = '';
    document.getElementById('form-cat-nombre').value = '';
    document.getElementById('form-cat-icono').value = '📌';
    document.getElementById('form-cat-color').value = '#FF6384';
    document.getElementById('form-cat-color-hex').textContent = '#FF6384';
    document.getElementById('modal-categoria').style.display = 'flex';
}

function abrirEditarCategoria(nombre) {
    document.getElementById('modal-cat-titulo').textContent = 'Editar Categoria';
    document.getElementById('form-cat-nombre-original').value = nombre;
    document.getElementById('form-cat-nombre').value = nombre;
    const icono = getIconoCat(nombre);
    const color = getColorCat(nombre);
    document.getElementById('form-cat-icono').value = icono;
    document.getElementById('form-cat-color').value = color;
    document.getElementById('form-cat-color-hex').textContent = color;
    document.getElementById('modal-categoria').style.display = 'flex';
}

function cerrarModalCategoria(e) {
    if (e && e.target && e.target !== e.currentTarget) return;
    document.getElementById('modal-categoria').style.display = 'none';
}

function guardarCategoria(e) {
    e.preventDefault();
    const nombreActual = document.getElementById('form-cat-nombre-original').value;
    const nombreNuevo = document.getElementById('form-cat-nombre').value.trim();
    const icono = document.getElementById('form-cat-icono').value.trim();
    const color = document.getElementById('form-cat-color').value;

    if (!nombreNuevo) { alert('Nombre requerido'); return; }

    const saveConfig = () => {
        const nombreFinal = document.getElementById('form-cat-nombre').value.trim();
        return fetch('/api/categorias/config', {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({nombre: nombreFinal, icono, color})
        });
    };

    if (nombreActual) {
        let chain = saveConfig();
        if (nombreActual !== nombreNuevo) {
            chain = chain.then(() => fetch('/api/categorias/rename', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({viejo: nombreActual, nuevo: nombreNuevo})
            }));
        }
        chain.then(() => { cargarCategorias(); cerrarModalCategoria(); });
    } else {
        alert('Usa "Añadir Transacción" desde Inicio para crear una transaccion en la nueva categoria');
        cerrarModalCategoria();
    }
}

document.addEventListener('DOMContentLoaded', () => {
    const cp = document.getElementById('form-cat-color');
    if (cp) cp.addEventListener('input', () => {
        document.getElementById('form-cat-color-hex').textContent = cp.value;
    });
});

function abrirCatTx(categoria) {
    document.getElementById('cat-tx-titulo').textContent = categoria;
    document.getElementById('cat-tx-desde').value = '';
    document.getElementById('cat-tx-hasta').value = '';
    document.getElementById('cat-tx-orden').value = 'fecha';
    document.getElementById('cat-tx-dir').value = 'true';
    document.getElementById('modal-cat-tx').style.display = 'flex';
    cargarCatTx();
}

function cerrarModalCatTx(e) {
    if (e && e.target && e.target !== e.currentTarget) return;
    document.getElementById('modal-cat-tx').style.display = 'none';
}

function cargarCatTx() {
    const categoria = document.getElementById('cat-tx-titulo').textContent;
    let params = `categoria=${encodeURIComponent(categoria)}`;
    const desde = document.getElementById('cat-tx-desde').value;
    const hasta = document.getElementById('cat-tx-hasta').value;
    if (desde) params += `&desde=${desde}`;
    if (hasta) params += `&hasta=${hasta}`;
    const select = document.getElementById('cat-tx-metodo');
    const selected = Array.from(select.selectedOptions).map(o => o.value);
    if (selected.length > 0) params += `&metodo_pago=${selected.join(',')}`;
    params += `&orden=${document.getElementById('cat-tx-orden').value}`;
    params += `&desc=${document.getElementById('cat-tx-dir').value}`;

    fetch(`/api/categorias/transacciones?${params}`)
        .then(r => r.json())
        .then(data => {
            catTxData = data.transacciones;
            document.getElementById('cat-tx-total').innerHTML = `<strong>Total: ${data.total_fmt}</strong> &middot; ${data.num_transacciones} transacciones`;
            const container = document.getElementById('cat-tx-lista');
            if (data.transacciones.length === 0) {
                container.innerHTML = '<div class="detalle-loading">Sin transacciones</div>';
                return;
            }
            container.innerHTML = data.transacciones.map(t => {
                const fecha = t.fecha_date ? new Date(t.fecha_date + 'T12:00:00').toLocaleDateString('es-CO', { day: 'numeric', month: 'short', year: 'numeric' }) : t.fecha;
                const metodoLabel = {efectivo: '💵', tarjeta_credito: '💳', transferencia: '🏦'}[t.metodo_pago] || '';
                const notas = t.notas ? `<div class="tx-nota">📝 ${t.notas}</div>` : '';
                const tags = (t.tags || []).map(tag => `<span class="tag-badge" style="background:${tag.color}20;color:${tag.color};border-color:${tag.color}">${tag.nombre}</span>`).join(' ');
                let cuotaBadge = '';
                if (t.es_cuota && t.cuota_info) {
                    cuotaBadge = `<span class="tx-cuota-badge">${t.cuota_info.cuota_actual}/${t.cuota_info.total_cuotas}</span>`;
                }
                return `<div class="detalle-tx" onclick="abrirDetalleTx(this, ${t.id})">
                    <span class="tx-icono">${metodoLabel}</span>
                    <div class="tx-body">
                        <span class="tx-desc">${t.descripcion || '—'} ${cuotaBadge}</span>
                        <span class="tx-fecha">${fecha}</span>
                        ${notas}
                        ${tags ? `<div class="tx-tags">${tags}</div>` : ''}
                    </div>
                    <span class="tx-valor ${t.valor < 0 ? 'negativo' : 'positivo'}">${t.valor_fmt}</span>
                    <button class="btn-icon btn-tag" onclick="event.stopPropagation();abrirDetalleTx(this, ${t.id})" title="Detalle">🔍</button>
                    <div class="tx-detail" id="tx-detail-cat-${t.id}" style="display:none">
                        <div class="tx-detail-inner">
                            <div class="tx-detail-row"><span>Método</span><span>${metodoLabel} ${t.metodo_pago || '—'}</span></div>
                            <div class="tx-detail-row"><span>Entidad</span><span>${t.entidad || '—'}</span></div>
                            <div class="tx-detail-row">
                                <span>Notas</span>
                                <span class="nota-view" id="nota-view-cat-${t.id}">
                                    ${t.notas
                                        ? `<span class="nota-text" onclick="editarNotaCat(${t.id})">📝 ${t.notas}</span><button class="btn-icon nota-edit-btn" onclick="event.stopPropagation();editarNotaCat(${t.id})" title="Editar nota">✏️</button>`
                                        : `<span class="nota-text nota-vacia" onclick="editarNotaCat(${t.id})">➕ Añadir nota</span><button class="btn-icon nota-edit-btn" onclick="event.stopPropagation();editarNotaCat(${t.id})" title="Añadir nota">✏️</button>`
                                    }
                                </span>
                            </div>
                            ${t.es_cuota && t.cuota_info ? `
                            <div class="tx-detail-row"><span>Cuota</span><span>${t.cuota_info.cuota_actual} de ${t.cuota_info.total_cuotas}</span></div>
                            <div class="tx-detail-row"><span>Valor total</span><span>$${Number(t.cuota_info.valor_total || 0).toLocaleString('es-CO')}</span></div>
                            <div class="tx-detail-row"><span>Compra</span><span>${t.cuota_info.compra_desc}</span></div>
                            ` : ''}
                            ${tags ? `<div class="tx-detail-row"><span>Etiquetas</span><span>${tags}</span></div>` : ''}
                            <div class="tx-detail-actions">
                                <button class="btn-icon" onclick="event.stopPropagation();abrirAsignarEtiquetasCat(${t.id})" title="Etiquetas">🏷️</button>
                            </div>
                        </div>
                    </div>
                </div>`;
            }).join('');
        })
        .catch(() => document.getElementById('cat-tx-lista').innerHTML = '<div class="detalle-loading">Error</div>');
}

let tagTxId = null;

function cargarEtiquetas() {
    fetch('/api/etiquetas')
        .then(r => r.json())
        .then(data => { etiquetasData = data; });
}

function abrirModalEtiquetas() {
    document.getElementById('modal-etiquetas').style.display = 'flex';
    renderEtiquetas();
}

function cerrarModalEtiquetas(e) {
    if (e && e.target && e.target !== e.currentTarget) return;
    document.getElementById('modal-etiquetas').style.display = 'none';
}

function renderEtiquetas() {
    const container = document.getElementById('etiquetas-lista');
    if (etiquetasData.length === 0) {
        container.innerHTML = '<div class="detalle-loading">Sin etiquetas. Crea una nueva.</div>';
        return;
    }
    container.innerHTML = etiquetasData.map(e => `
        <div class="etiqueta-item">
            <span class="tag-badge" style="background:${e.color}20;color:${e.color};border-color:${e.color}">${e.nombre}</span>
            <div class="etiqueta-acciones">
                <button class="btn-icon" onclick="abrirEditarEtiqueta(${e.id}, '${e.nombre}', '${e.color}')" title="Editar">✏️</button>
                <button class="btn-icon" onclick="eliminarEtiqueta(${e.id})" title="Eliminar">🗑️</button>
            </div>
        </div>
    `).join('');
}

function abrirNuevaEtiqueta() {
    document.getElementById('modal-etq-titulo').textContent = 'Nueva Etiqueta';
    document.getElementById('form-etq-id').value = '';
    document.getElementById('form-etq-nombre').value = '';
    document.getElementById('form-etq-color').value = '#6B7280';
    document.getElementById('form-etq-color-hex').textContent = '#6B7280';
    document.getElementById('modal-etiqueta-form').style.display = 'flex';
}

function abrirEditarEtiqueta(id, nombre, color) {
    document.getElementById('modal-etq-titulo').textContent = 'Editar Etiqueta';
    document.getElementById('form-etq-id').value = id;
    document.getElementById('form-etq-nombre').value = nombre;
    document.getElementById('form-etq-color').value = color;
    document.getElementById('form-etq-color-hex').textContent = color;
    document.getElementById('modal-etiqueta-form').style.display = 'flex';
}

function cerrarModalEtiquetaForm(e) {
    if (e && e.target && e.target !== e.currentTarget) return;
    document.getElementById('modal-etiqueta-form').style.display = 'none';
}

function guardarEtiqueta(e) {
    e.preventDefault();
    const id = document.getElementById('form-etq-id').value;
    const nombre = document.getElementById('form-etq-nombre').value.trim();
    const color = document.getElementById('form-etq-color').value;
    if (!nombre) { alert('Nombre requerido'); return; }

    if (id) {
        fetch('/api/etiquetas/' + id, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({nombre, color})
        }).then(r => r.json()).then(() => {
            cargarEtiquetas();
            cerrarModalEtiquetaForm();
            renderEtiquetas();
        });
    } else {
        fetch('/api/etiquetas', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({nombre, color})
        }).then(r => r.json()).then(() => {
            cargarEtiquetas();
            cerrarModalEtiquetaForm();
            renderEtiquetas();
        });
    }
}

function eliminarEtiqueta(id) {
    if (!confirm('Eliminar esta etiqueta?')) return;
    fetch('/api/etiquetas/' + id, {method: 'DELETE'})
        .then(r => r.json()).then(() => {
            cargarEtiquetas();
            renderEtiquetas();
        });
}

document.addEventListener('DOMContentLoaded', () => {
    const cp = document.getElementById('form-etq-color');
    if (cp) cp.addEventListener('input', () => {
        document.getElementById('form-etq-color-hex').textContent = cp.value;
    });
});

function abrirAsignarEtiquetas(txId, txDesc) {
    tagTxId = txId;
    document.getElementById('tag-tx-titulo').textContent = 'Etiquetas — ' + txDesc;
    document.getElementById('modal-tag-tx').style.display = 'flex';
    renderTagAsignacion();
}

function cerrarModalTagTx(e) {
    if (e && e.target && e.target !== e.currentTarget) return;
    document.getElementById('modal-tag-tx').style.display = 'none';
    tagTxId = null;
}

function renderTagAsignacion() {
    const container = document.getElementById('etiquetas-grid');
    if (!tagTxId) return;
    fetch('/api/transacciones/' + tagTxId + '/etiquetas')
        .then(r => r.json())
        .then(txTags => {
            const txTagIds = txTags.map(t => t.id);
            container.innerHTML = etiquetasData.map(e => {
                const asignada = txTagIds.includes(e.id);
                return `<button class="etiqueta-asignar ${asignada ? 'asignada' : ''}"
                    onclick="toggleEtiquetaTx(${tagTxId}, ${e.id}, ${asignada})"
                    style="background:${asignada ? e.color+'40' : 'var(--bg)'};border-color:${e.color}">
                    <span class="tag-badge" style="background:${e.color}20;color:${e.color};border-color:${e.color}">${e.nombre}</span>
                    <span class="etq-check">${asignada ? '✓' : '+'}</span>
                </button>`;
            }).join('');
        });
}

function toggleEtiquetaTx(txId, etqId, asignada) {
    if (asignada) {
        fetch('/api/transacciones/' + txId + '/etiquetas/' + etqId, {method: 'DELETE'})
            .then(r => r.json()).then(() => renderTagAsignacion());
    } else {
        fetch('/api/transacciones/' + txId + '/etiquetas', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({etiqueta_id: etqId})
        }).then(r => r.json()).then(() => renderTagAsignacion());
    }
}

function abrirDetalleTx(el, txId) {
    const detail = document.getElementById('tx-detail-cat-' + txId);
    if (!detail) return;
    document.querySelectorAll('.tx-detail[id^="tx-detail-cat-"]').forEach(d => {
        if (d.id !== 'tx-detail-cat-' + txId) d.style.display = 'none';
    });
    detail.style.display = detail.style.display === 'none' ? 'block' : 'none';
}

function abrirAsignarEtiquetasCat(txId) {
    const detail = document.getElementById('tx-detail-cat-' + txId);
    if (!detail) return;
    const actionsDiv = detail.querySelector('.tx-detail-actions');
    if (!actionsDiv) return;
    const existing = detail.querySelector('.tx-detail-tag-picker');
    if (existing) { existing.remove(); return; }
    if (typeof etiquetasData === 'undefined' || etiquetasData.length === 0) {
        alert('No hay etiquetas. Crea una primero.');
        return;
    }
    const picker = document.createElement('div');
    picker.className = 'tx-detail-tag-picker';
    actionsDiv.appendChild(picker);
    fetch('/api/transacciones/' + txId + '/etiquetas')
        .then(r => r.json())
        .then(txTags => {
            const tagIds = txTags.map(tg => tg.id);
            picker.innerHTML = etiquetasData.map(e => {
                const assigned = tagIds.includes(e.id);
                return `<button class="tag-pick-btn ${assigned ? 'assigned' : ''}"
                    data-etq-id="${e.id}"
                    style="background:${e.color}20;border-color:${e.color}"
                    onclick="toggleTagTxCat(${txId}, ${e.id}, this)">
                    <span style="color:${e.color}">${e.nombre}</span>
                </button>`;
            }).join('');
        });
}

function toggleTagTxCat(txId, etqId, btn) {
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

function editarNotaCat(txId) {
    event.stopPropagation();
    const viewEl = document.getElementById('nota-view-cat-' + txId);
    if (!viewEl) return;
    const textSpan = viewEl.querySelector('.nota-text');
    const currentText = textSpan ? textSpan.textContent.replace(/^[📝➕]\s*/, '') : '';
    viewEl.dataset.originalNota = currentText;
    viewEl.innerHTML = `<textarea rows="2" class="nota-textarea">${currentText.replace(/</g, '&lt;')}</textarea>
        <div class="nota-actions">
            <button class="btn-cruzar sm" onclick="event.stopPropagation();guardarNotaCat(${txId})">Guardar</button>
            <button class="btn-cancelar" onclick="event.stopPropagation();cancelarNotaCat(${txId})">Cancelar</button>
        </div>`;
    const ta = viewEl.querySelector('textarea');
    if (ta) { ta.focus(); ta.select(); }
}

function guardarNotaCat(txId) {
    const viewEl = document.getElementById('nota-view-cat-' + txId);
    if (!viewEl) return;
    const ta = viewEl.querySelector('textarea');
    if (!ta) return;
    const notas = ta.value.trim();
    fetch('/api/transacciones/' + txId + '/notas', {
        method: 'PUT',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({notas})
    }).then(r => r.json()).then(data => {
        if (data.ok) {
            const escNotas = notas.replace(/</g, '&lt;');
            if (notas) {
                viewEl.innerHTML = `<span class="nota-text" onclick="editarNotaCat(${txId})">📝 ${escNotas}</span><button class="btn-icon nota-edit-btn" onclick="event.stopPropagation();editarNotaCat(${txId})" title="Editar nota">✏️</button>`;
            } else {
                viewEl.innerHTML = `<span class="nota-text nota-vacia" onclick="editarNotaCat(${txId})">➕ Añadir nota</span><button class="btn-icon nota-edit-btn" onclick="event.stopPropagation();editarNotaCat(${txId})" title="Añadir nota">✏️</button>`;
            }
            const detalleTx = viewEl.closest('.detalle-tx');
            if (detalleTx) {
                const notaDiv = detalleTx.querySelector('.tx-nota');
                if (notaDiv) {
                    if (notas) notaDiv.innerHTML = '📝 ' + escNotas;
                    else notaDiv.remove();
                } else if (notas) {
                    const newNota = document.createElement('div');
                    newNota.className = 'tx-nota';
                    newNota.innerHTML = '📝 ' + escNotas;
                    const txBody = detalleTx.querySelector('.tx-body');
                    const tagsDiv = txBody ? txBody.querySelector('.tx-tags') : null;
                    if (tagsDiv) {
                        txBody.insertBefore(newNota, tagsDiv);
                    } else if (txBody) {
                        txBody.appendChild(newNota);
                    }
                }
            }
        }
    });
}

function cancelarNotaCat(txId) {
    const viewEl = document.getElementById('nota-view-cat-' + txId);
    if (!viewEl) return;
    const originalNota = viewEl.dataset.originalNota || '';
    const escOriginal = originalNota.replace(/</g, '&lt;');
    if (originalNota) {
        viewEl.innerHTML = `<span class="nota-text" onclick="editarNotaCat(${txId})">📝 ${escOriginal}</span><button class="btn-icon nota-edit-btn" onclick="event.stopPropagation();editarNotaCat(${txId})" title="Editar nota">✏️</button>`;
    } else {
        viewEl.innerHTML = `<span class="nota-text nota-vacia" onclick="editarNotaCat(${txId})">➕ Añadir nota</span><button class="btn-icon nota-edit-btn" onclick="event.stopPropagation();editarNotaCat(${txId})" title="Añadir nota">✏️</button>`;
    }
    delete viewEl.dataset.originalNota;
}

document.addEventListener('DOMContentLoaded', () => {
    const multi = document.getElementById('cat-tx-metodo');
    if (multi) {
        multi.addEventListener('mousedown', function(e) {
            if (e.target.tagName === 'OPTION') {
                e.preventDefault();
                e.target.selected = !e.target.selected;
                cargarCatTx();
            }
        });
    }
});

document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        ['modal-categoria', 'modal-cat-tx', 'modal-etiquetas', 'modal-etiqueta-form', 'modal-tag-tx'].forEach(id => {
            const el = document.getElementById(id);
            if (el && el.style.display !== 'none') el.style.display = 'none';
        });
    }
});
