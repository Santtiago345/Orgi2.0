"""
ANALISIS COMPLETO DE TARJETAS DE CREDITO (RappiCard + Nu)
Genera para cada entidad:
  - analisis_{entidad}.json       (extractos con datos completos)
  - reporte_{entidad}.txt         (reporte en texto)
  - {entidad}_transacciones_completo.json  (transacciones detalladas)
  - {entidad}_finanzas.db         (base de datos SQLite)

Fuente: finanzas_unificadas.db + finanzas_unificada_completa.db
"""

import os, re, json, sqlite3
from collections import defaultdict
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_UNIFICADA = os.path.join(BASE, 'outputs', 'db', 'finanzas_unificadas.db')
DB_COMPLETA  = os.path.join(BASE, 'outputs', 'db', 'finanzas_unificada_completa.db')


MESES = {'ENE':1,'FEB':2,'MAR':3,'ABR':4,'MAY':5,'JUN':6,
         'JUL':7,'AGO':8,'SEP':9,'OCT':10,'NOV':11,'DIC':12,
         'ENERO':1,'FEBRERO':2,'MARZO':3,'ABRIL':4,'MAYO':5,'JUNIO':6,
         'JULIO':7,'AGOSTO':8,'SEPTIEMBRE':9,'OCTUBRE':10,'NOVIEMBRE':11,'DICIEMBRE':12}


def parse_periodo_fechas(periodo):
    """Parsear '30 abr 2026 a 28 may 2026' a (start_date, end_date) en formato YYYY-MM-DD."""
    if not periodo:
        return None, None
    m = re.match(r'(\d{1,2})\s+(\w{3,})\s+(\d{4})\s+a\s+(\d{1,2})\s+(\w{3,})\s+(\d{4})', periodo.lower())
    if m:
        d1, mon1, y1 = int(m.group(1)), MESES.get(m.group(2)[:3].upper()), int(m.group(3))
        d2, mon2, y2 = int(m.group(4)), MESES.get(m.group(5)[:3].upper()), int(m.group(6))
        if mon1 and mon2:
            return f'{y1:04d}-{mon1:02d}-{d1:02d}', f'{y2:04d}-{mon2:02d}-{d2:02d}'
    m = re.match(r'(\d{1,2})\s+(\w{3,})\s+a\s+(\d{1,2})\s+(\w{3,})\s+(\d{4})', periodo.lower())
    if m:
        d1, mon1 = int(m.group(1)), MESES.get(m.group(2)[:3].upper())
        d2, mon2, y2 = int(m.group(3)), MESES.get(m.group(4)[:3].upper()), int(m.group(5))
        if mon1 and mon2:
            y1 = y2 if mon1 <= mon2 else y2 - 1
            return f'{y1:04d}-{mon1:02d}-{d1:02d}', f'{y2:04d}-{mon2:02d}-{d2:02d}'
    return None, None


def formatear_valor(v):
    if v is None: return 'N/A'
    return f"${v:,.2f}"


def clasificar_tarjeta(desc):
    d = desc.upper().strip()
    if any(k in d for k in ['TIENDAS ARA','SURTITODO','D1','OXXO','EXITO',
                            'CARULLA','JUMBO','MERCADOPAGO','LA SALCHIPAPERIA',
                            'PAPA JOHNS','MC DONALD','MCDONALD','KFC','RAPPI',
                            'DIDI FOOD','HAMBURGUES','COMIDA','ALIMENTO',
                            'PANADERIA','DUNKIN','SANDWICH','STARBUCKS',
                            'PRAGA','SUBS WAY','SUBWAY','PIZZA','CARNES',
                            'FRUVER','MULTIAHORRO','MERCADO']):
        return 'Comida'
    if any(k in d for k in ['KOAJ','HYM','ADIDAS','NIKE','ZARA','TRENDY SHOP',
                            'DOLLARCITY','FALABELLA','CUIDADO CON EL PERRO']):
        return 'Ropa'
    if any(k in d for k in ['TIGO','UNE TELCO','NETFLIX','SPOTIFY','BOLD',
                            'CLARO','MOVISTAR','CASHBACK']):
        return 'Servicios'
    if any(k in d for k in ['UNAL','UNIVERSIDAD','ICETEX','MATRICULA','U. NACIONAL']):
        return 'Educacion'
    if any(k in d for k in ['FARMACIA','DROGUERIA','MEDICO','EPS','CLINICA',
                            'FARMASHOP','FARMEDICAL','DENTAL']):
        return 'Salud'
    if any(k in d for k in ['FORTNITE','EPIC','PLAYSTATION','TUBOLETA','CINE',
                            'BOOMERANG','CERVEZA','LICORES']):
        return 'Entretenimiento'
    if any(k in d for k in ['APPLE','AMZN','AMAZON','MERCADO LIBRE','LINIO',
                            'ALIEXPRESS','LOGITECH','HUAWEI']):
        return 'Tecnologia'
    if any(k in d for k in ['VIA MOTOS','TALLER DE','GASOLINA','MOTO',
                            'PRIMAX','ESTACION','CABIFY','UBER','TAXI','TRANSPORTE']):
        return 'Transporte'
    if any(k in d for k in ['HOTEL','AIRBNB','VUELO','VIAJE','DESPEGAR']):
        return 'Viajes'
    if any(k in d for k in ['MINISO','CASAMILAS','ESPACIO NATURA','ZONA DE MODA']):
        return 'Compras general'
    if any(k in d for k in ['AJUSTE COMPRA','INTERES','CUOTA DE MANEJO']):
        return 'Cargos financieros'
    if d.startswith('COMPRA EN ') or d.startswith('COMPRA '):
        return 'Compras general'
    return 'Sin clasificar'


def main():
    print('=' * 70)
    print('ANALISIS COMPLETO DE TARJETAS DE CREDITO')
    print('=' * 70)
    
    conn_uni = sqlite3.connect(DB_UNIFICADA)
    conn_uni.row_factory = sqlite3.Row
    conn_com = sqlite3.connect(DB_COMPLETA)
    conn_com.row_factory = sqlite3.Row
    
    for fuente in ['rappicard', 'nu']:
        print(f'\n--- Procesando {fuente.upper()} ---')
        
        # --- CARGAR DATOS ---
        c = conn_uni.cursor()
        c.execute('SELECT * FROM extractos WHERE fuente=? ORDER BY id', (fuente,))
        extractos = [dict(r) for r in c.fetchall()]
        
        c = conn_com.cursor()
        c.execute('SELECT * FROM transacciones WHERE entidad=? ORDER BY fecha', (fuente,))
        txs_completa = [dict(r) for r in c.fetchall()]
        
        c = conn_com.cursor()
        c.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='correcciones_extractos'")
        if c.fetchone():
            c.execute('SELECT * FROM correcciones_extractos')
            correcs = {r['extracto_id']: dict(r) for r in c.fetchall()}
        else:
            correcs = {}
        
        print(f'  Extractos: {len(extractos)}')
        print(f'  Transacciones (completa): {len(txs_completa)}')
        print(f'  Correcciones: {len(correcs)}')
        
        # --- MAPEAR TRANSACCIONES A EXTRACTOS POR FECHA ---
        ext_fechas = []
        for e in extractos:
            sd, ed = parse_periodo_fechas(e.get('periodo', ''))
            ext_fechas.append((e, sd, ed))
        
        for tx in txs_completa:
            tx_date = tx.get('fecha', '')[:10]
            tx['extracto_ids'] = []
            for e, sd, ed in ext_fechas:
                if sd and ed and sd <= tx_date <= ed:
                    tx['extracto_ids'].append(e['id'])
            tx['extracto_id_ppal'] = tx['extracto_ids'][0] if tx['extracto_ids'] else None
        
        # --- CONSTRUIR ANALISIS ---
        analisis = []
        
        for e, sd, ed in ext_fechas:
            ext_id = e['id']
            txs_ext = [tx for tx in txs_completa if ext_id in tx.get('extracto_ids', [])]
            
            item = {
                'archivo': e.get('archivo', ''),
                'periodo': e.get('periodo', ''),
                'anio': e.get('anio'),
                'mes': e.get('mes'),
                'titular': e.get('titular', ''),
                'tipo': 'Tarjeta Credito RappiCard Davivienda' if fuente == 'rappicard' else 'Tarjeta Credito Nu Bank',
                'total_pagar': e.get('total_pagar'),
                'pago_minimo': e.get('pago_minimo'),
                'cupo_total': e.get('cupo_total'),
                'saldo_anterior': e.get('saldo_anterior'),
                'fecha_corte': e.get('fecha_corte'),
                'fecha_pago': e.get('fecha_pago'),
                'num_transacciones': len(txs_ext),
            }
            
            # Correcciones / intereses
            if ext_id in correcs:
                cr = correcs[ext_id]
                item['pago_minimo_original'] = cr.get('pago_minimo_original')
                item['pago_minimo_corregido'] = cr.get('pago_minimo_corregido')
                item['interes_corriente'] = cr.get('interes_corriente')
                item['tasa_mensual'] = cr.get('tasa_mensual')
                item['tasa_anual_ea'] = cr.get('tasa_anual_ea')
                item['es_refinanciacion'] = bool(cr.get('es_refinanciacion'))
                item['notas_correccion'] = cr.get('notas')
            
            # Transacciones
            item['transacciones'] = []
            for tx in txs_ext:
                nc = tx.get('num_cuotas', 1) or 1
                cp = tx.get('cuotas_pagadas', 1) or 1
                monto = abs(tx.get('monto', 0))
                
                cap_pend = None
                if nc > 1 and cp < nc:
                    valor_cuota = monto / nc
                    cap_pend = round(valor_cuota * (nc - cp), 2)
                
                estado = tx.get('estado_pago', 'pagada')
                cuota_act = cp if estado == 'pagada' else min(cp + 1, nc)
                
                item['transacciones'].append({
                    'fecha': tx.get('fecha', ''),
                    'descripcion': tx.get('descripcion', ''),
                    'valor': -monto,
                    'categoria': clasificar_tarjeta(tx.get('descripcion', '')),
                    'cuota_actual': cuota_act,
                    'total_cuotas': nc,
                    'capital_pendiente': cap_pend,
                    'estado_pago': estado,
                })
            
            analisis.append(item)
        
        # --- REPORTE TEXTO ---
        NOMBRE = 'JOEL SANTIAGO NEUTA JASPE'
        lines = []
        lines.append('=' * 75)
        lines.append(f'REPORTE DE ANALISIS - {"RappiCard Davivienda" if fuente == "rappicard" else "Nu Bank"}')
        lines.append(f'Titular: {NOMBRE}')
        lines.append('=' * 75)
        lines.append(f'Total extractos: {len(analisis)}')
        lines.append('')
        
        # Coverage matrix
        years = sorted(set(e['anio'] for e in analisis if e['anio']))
        lines.append('--- MATRIZ DE COBERTURA ---')
        if years:
            lines.append('Periodo    Ene-Feb-Mar-Abr-May-Jun   Jul-Ago-Sep-Oct-Nov-Dic')
            lines.append('-' * 55)
            for y in years:
                cov = {e['mes']: 'OK' for e in analisis if e['anio'] == y and e['mes']}
                row1 = ' '.join(cov.get(m, '--') for m in range(1, 7))
                row2 = ' '.join(cov.get(m, '--') for m in range(7, 13))
                lines.append(f'{y}        {row1}   {row2}')
        
        all_months = set((e['anio'], e['mes']) for e in analisis if e['anio'] and e['mes'])
        missing = []
        for y in range(min(years or [2025]), max(years or [2026]) + 1):
            for m in range(1, 13):
                if (y, m) not in all_months:
                    missing.append(f'{list(MESES.keys())[m-1][:3]} {y}')
        if missing:
            lines.append('')
            lines.append('Meses faltantes:')
            for m in missing:
                lines.append(f'  - {m}')
        
        # Global summary
        lines.append('')
        lines.append('--- RESUMEN GLOBAL ---')
        total_pagar = sum(e.get('total_pagar') or 0 for e in analisis)
        total_min = sum(e.get('pago_minimo') or 0 for e in analisis)
        total_tx = sum(e['num_transacciones'] for e in analisis)
        lines.append(f'Total a pagar acumulado: {formatear_valor(total_pagar)}')
        lines.append(f'Total pago minimo acumulado: {formatear_valor(total_min)}')
        lines.append(f'Total transacciones: {total_tx}')
        cupos = [e.get('cupo_total') for e in analisis if e.get('cupo_total')]
        if cupos:
            lines.append(f'Cupo total: {formatear_valor(max(cupos))}')
        
        # Interest analysis
        lines.append('')
        lines.append('--- ANALISIS DE INTERESES ---')
        for e in analisis:
            interes = e.get('interes_corriente')
            tasa_m = e.get('tasa_mensual')
            tasa_ea = e.get('tasa_anual_ea')
            refi = e.get('es_refinanciacion', False)
            refi_str = ' [REFINANCIACION]' if refi else ''
            if interes:
                lines.append(f'  {e["periodo"]}: interes={interes:.2f}{refi_str}')
            else:
                lines.append(f'  {e["periodo"]}: Sin datos de interes')
        
        # Monthly detail
        lines.append('')
        lines.append('--- DETALLE MENSUAL ---')
        for e in sorted(analisis, key=lambda x: (x['anio'] or 0, x['mes'] or 0)):
            lines.append('')
            lines.append(f'>> {e["periodo"]} | Total: {formatear_valor(e["total_pagar"])} | Minimo: {formatear_valor(e["pago_minimo"])} | Tx: {e["num_transacciones"]}')
            if e.get('cupo_total'):
                lines.append(f'   Cupo: {formatear_valor(e["cupo_total"])}')
            if e.get('fecha_pago'):
                lines.append(f'   Fecha pago: {e["fecha_pago"]}')
            if e.get('saldo_anterior'):
                lines.append(f'   Saldo anterior: {formatear_valor(e["saldo_anterior"])}')
            if e.get('interes_corriente'):
                lines.append(f'   Interes corriente: {formatear_valor(e["interes_corriente"])}')
                if e.get('es_refinanciacion'):
                    lines.append('   *** REFINANCIACION ***')
            
            # Top 5
            txs = sorted(e['transacciones'], key=lambda t: abs(t['valor']), reverse=True)[:5]
            if txs:
                lines.append('')
                lines.append('   Top 5 transacciones:')
                for t in txs:
                    cuo = f' ({t["cuota_actual"]}/{t["total_cuotas"]})' if t['total_cuotas'] > 1 else ''
                    lines.append(f'     [{t["fecha"]}] {t["descripcion"][:45]:45s} {formatear_valor(t["valor"])}{cuo}')
            
            # Compras en cuotas
            cuotas_txs = [t for t in e['transacciones'] if t['total_cuotas'] > 1]
            if cuotas_txs:
                lines.append('')
                lines.append('   Compras en cuotas en este periodo:')
                for t in cuotas_txs:
                    pend = f' | Pend: {formatear_valor(t["capital_pendiente"])}' if t.get('capital_pendiente') else ' | Pagada'
                    lines.append(f'     [{t["fecha"]}] {t["descripcion"][:40]:40s} {formatear_valor(t["valor"])} ({t["cuota_actual"]}/{t["total_cuotas"]}){pend}')
        
        # All deferred purchases
        lines.append('')
        lines.append('--- COMPRAS DIFERIDAS (CUOTAS) ---')
        all_cuotas = []
        for e in analisis:
            for t in e['transacciones']:
                if t['total_cuotas'] > 1:
                    all_cuotas.append(t)
        seen = set()
        for t in all_cuotas:
            key = (t['descripcion'].upper().strip(), round(abs(t['valor']), 0))
            if key not in seen:
                seen.add(key)
                pend = f' - Pend: {formatear_valor(t["capital_pendiente"])}' if t.get('capital_pendiente') else ' - Pagada'
                lines.append(f'  {t["descripcion"][:40]:40s} {formatear_valor(t["valor"])} ({t["cuota_actual"]}/{t["total_cuotas"]}){pend}')
        if not all_cuotas:
            lines.append('  No hay compras en cuotas')
        
        # By category
        lines.append('')
        lines.append('--- GASTOS POR CATEGORIA ---')
        cat_totals = defaultdict(float)
        cat_counts = defaultdict(int)
        for e in analisis:
            for t in e['transacciones']:
                cat_totals[t['categoria']] += abs(t['valor'])
                cat_counts[t['categoria']] += 1
        for cat, total in sorted(cat_totals.items(), key=lambda x: -x[1]):
            pct = total / sum(cat_totals.values()) * 100 if sum(cat_totals.values()) > 0 else 0
            lines.append(f'  {cat:25s} {cat_counts[cat]:4d} tx  {formatear_valor(total):>15s}  ({pct:5.1f}%)')
        lines.append(f'  {"TOTAL":25s} {sum(cat_counts.values()):4d} tx  {formatear_valor(sum(cat_totals.values()))}')
        
        lines.append('')
        lines.append('=' * 75)
        lines.append('FIN DEL REPORTE')
        lines.append('=' * 75)
        reporte = '\n'.join(lines)
        
        # --- TRANSACCIONES COMPLETO JSON ---
        txc = {
            'fuente': fuente,
            'tipo': 'Tarjeta Credito' + (' RappiCard Davivienda' if fuente == 'rappicard' else ' Nu Bank'),
            'extractos': [],
            'transacciones': [],
            'categorias': [],
            'compras_diferidas': [],
        }
        for e in analisis:
            txc['extractos'].append({
                'id': (e.get('anio') or 0) * 100 + (e.get('mes') or 0),
                'archivo': e['archivo'],
                'periodo': e['periodo'],
                'anio': e['anio'],
                'mes': e['mes'],
                'total_pagar': e['total_pagar'],
                'pago_minimo': e['pago_minimo'],
                'cupo_total': e.get('cupo_total'),
                'fecha_pago': e.get('fecha_pago'),
                'interes_corriente': e.get('interes_corriente'),
                'es_refinanciacion': e.get('es_refinanciacion', False),
                'num_transacciones': e['num_transacciones'],
            })
            for t in e['transacciones']:
                txc['transacciones'].append({
                    'extracto_periodo': e['periodo'],
                    'fecha': t['fecha'],
                    'descripcion': t['descripcion'],
                    'descripcion_normalizada': re.sub(r'[^A-Z0-9\s]', '', t['descripcion'].upper()).strip(),
                    'valor': t['valor'],
                    'categoria': t['categoria'],
                    'cuota_actual': t['cuota_actual'],
                    'total_cuotas': t['total_cuotas'],
                    'capital_pendiente': t.get('capital_pendiente'),
                    'estado_pago': t['estado_pago'],
                })
        cats = sorted(set(t['categoria'] for t in txc['transacciones']))
        for i, cat in enumerate(cats, 1):
            txc['categorias'].append({'id': i, 'nombre': cat, 'tipo': 'egreso'})
        seen_comp = set()
        for e in analisis:
            for t in e['transacciones']:
                if t['total_cuotas'] > 1:
                    key = (t['descripcion'].upper().strip(), round(abs(t['valor']), 0))
                    if key not in seen_comp:
                        seen_comp.add(key)
                        tc = t['total_cuotas']
                        ca = t['cuota_actual']
                        if t['estado_pago'] == 'pagada':
                            cuo_pag = tc
                        else:
                            cuo_pag = ca - 1  # en_curso: cuota_actual - 1 pagadas
                        txc['compras_diferidas'].append({
                            'descripcion': t['descripcion'],
                            'valor_total': abs(t['valor']),
                            'total_cuotas': tc,
                            'cuotas_pagadas': cuo_pag,
                            'capital_pendiente': t.get('capital_pendiente'),
                            'estado': t['estado_pago'],
                        })
        
        # --- BASE DE DATOS SQLITE ---
        data_dir = os.path.join(BASE, 'data', fuente)
        os.makedirs(data_dir, exist_ok=True)
        
        db_path = os.path.join(data_dir, f'{fuente}_finanzas.db')
        if os.path.exists(db_path):
            os.remove(db_path)
        db = sqlite3.connect(db_path)
        cur = db.cursor()
        
        cur.execute('''CREATE TABLE IF NOT EXISTS extractos (
            id INTEGER PRIMARY KEY, archivo TEXT, periodo TEXT, anio INTEGER, mes INTEGER,
            titular TEXT, total_pagar REAL, pago_minimo REAL, cupo_total REAL,
            saldo_anterior REAL, fecha_corte TEXT, fecha_pago TEXT,
            interes_corriente REAL, tasa_mensual REAL, tasa_anual_ea REAL,
            es_refinanciacion INTEGER DEFAULT 0, num_transacciones INTEGER)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS transacciones (
            id INTEGER PRIMARY KEY AUTOINCREMENT, extracto_id INTEGER,
            fecha TEXT, descripcion TEXT, descripcion_normalizada TEXT,
            valor REAL, categoria TEXT, cuota_actual INTEGER DEFAULT 1,
            total_cuotas INTEGER DEFAULT 1, capital_pendiente REAL,
            estado_pago TEXT DEFAULT 'pagada',
            FOREIGN KEY (extracto_id) REFERENCES extractos(id))''')
        cur.execute('''CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY, nombre TEXT UNIQUE, tipo TEXT)''')
        cur.execute('''CREATE TABLE IF NOT EXISTS compras_diferidas (
            id INTEGER PRIMARY KEY, descripcion TEXT, valor_total REAL,
            total_cuotas INTEGER, cuotas_pagadas INTEGER,
            capital_pendiente REAL, estado TEXT)''')
        
        for i, e in enumerate(analisis, 1):
            cur.execute('''INSERT INTO extractos VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (
                i, e['archivo'], e['periodo'], e['anio'], e['mes'], e['titular'],
                e['total_pagar'], e['pago_minimo'], e.get('cupo_total'),
                e.get('saldo_anterior'), e.get('fecha_corte'), e.get('fecha_pago'),
                e.get('interes_corriente'), e.get('tasa_mensual'), e.get('tasa_anual_ea'),
                1 if e.get('es_refinanciacion') else 0, e['num_transacciones']))
        
        tx_id = 1
        for i, e in enumerate(analisis, 1):
            for t in e['transacciones']:
                cur.execute('''INSERT INTO transacciones VALUES (?,?,?,?,?,?,?,?,?,?,?)''', (
                    tx_id, i, t['fecha'], t['descripcion'],
                    re.sub(r'[^A-Z0-9\s]', '', t['descripcion'].upper()).strip(),
                    t['valor'], t['categoria'], t['cuota_actual'], t['total_cuotas'],
                    t.get('capital_pendiente'), t['estado_pago']))
                tx_id += 1
        
        for i, cat in enumerate(cats, 1):
            cur.execute('INSERT OR IGNORE INTO categorias VALUES (?,?,?)', (i, cat, 'egreso'))
        
        for i, cd in enumerate(txc['compras_diferidas'], 1):
            cur.execute('''INSERT INTO compras_diferidas VALUES (?,?,?,?,?,?,?)''', (
                i, cd['descripcion'], cd['valor_total'], cd['total_cuotas'],
                cd['cuotas_pagadas'], cd['capital_pendiente'], cd['estado']))
        
        db.commit()
        db.close()
        
        # --- GUARDAR ARCHIVOS ---
        json_path = os.path.join(data_dir, f'analisis_{fuente}.json')
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(analisis, f, indent=2, ensure_ascii=False, default=str)
        print(f'  -> {json_path}')
        
        reporte_path = os.path.join(data_dir, f'reporte_{fuente}.txt')
        with open(reporte_path, 'w', encoding='utf-8') as f:
            f.write(reporte)
        print(f'  -> {reporte_path}')
        
        txc_path = os.path.join(data_dir, f'{fuente}_transacciones_completo.json')
        with open(txc_path, 'w', encoding='utf-8') as f:
            json.dump(txc, f, indent=2, ensure_ascii=False, default=str)
        print(f'  -> {txc_path}')
        
        print(f'  -> {db_path}')
        
        # Stats
        total_gastos = sum(abs(t['valor']) for e in analisis for t in e['transacciones'])
        cuotas_count = sum(1 for e in analisis for t in e['transacciones'] if t['total_cuotas'] > 1)
        print(f'  Total transacciones: {sum(e["num_transacciones"] for e in analisis)}')
        print(f'  Total gastos: ${total_gastos:,.2f}')
        print(f'  Compras en cuotas: {cuotas_count}')
    
    conn_uni.close()
    conn_com.close()
    
    print('\n' + '=' * 70)
    print('PROCESO COMPLETADO')
    print('=' * 70)


if __name__ == '__main__':
    main()
