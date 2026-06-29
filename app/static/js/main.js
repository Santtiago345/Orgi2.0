/* ORGI — Funcionalidad frontend */
// Las funciones principales están inline en index.html.
// Este archivo es para funciones globales/reutilizables.

console.log('Orgi App cargada');

// Cerrar modal con Escape
document.addEventListener('keydown', function(e) {
    if (e.key === 'Escape') {
        const modal = document.getElementById('modal-overlay');
        if (modal && modal.style.display !== 'none') {
            modal.style.display = 'none';
        }
    }
});
