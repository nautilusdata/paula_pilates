from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from .models import (Pack, Sesion, feriados_punta_arenas,
                     ConfiguracionGeneral, ConfiguracionPrecio,
                     ConfiguracionHorario)

# ─── Nombres ──────────────────────────────────────────────────────────────────

NOMBRE_DIA_LARGO = {
    0: 'Lunes', 1: 'Martes', 2: 'Miércoles',
    3: 'Jueves', 4: 'Viernes', 5: 'Sábado'
}
NOMBRE_DIA_CORTO = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
MES_ES = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril', 5: 'mayo', 6: 'junio',
    7: 'julio', 8: 'agosto', 9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
}

def fmt_fecha_bb(d: date) -> str:
    return f"{NOMBRE_DIA_CORTO[d.weekday()]} {d.day} {MES_ES[d.month]}"


# ─── Fuente de verdad: ConfiguracionHorario tipo BDB ─────────────────────────

def get_slots_bdb() -> list:
    """
    Lee de DB los slots BDB activos.
    Retorna lista de dicts con dia, hora, dia_nombre, label.
    """
    slots = (ConfiguracionHorario.objects
             .filter(tipo='BDB', activo=True)
             .order_by('dia', 'hora'))
    return [
        {
            'dia':       s.dia,
            'hora':      s.hora,
            'dia_nombre': NOMBRE_DIA_LARGO[s.dia],
            'label':     f"{NOMBRE_DIA_LARGO[s.dia]} {s.hora:02d}:00",
            'key':       str(s.dia),          # clave usada en el form
            'js_day':    s.dia + 1,           # JS: 0=Dom → python dia+1
        }
        for s in slots
    ]


def get_dia_hora_bdb() -> dict:
    """Retorna {weekday: hora} para los slots BDB activos."""
    slots = ConfiguracionHorario.objects.filter(tipo='BDB', activo=True)
    return {s.dia: s.hora for s in slots}


# ─── Helpers ──────────────────────────────────────────────────────────────────

def cupos_bb(fecha: date, hora: int) -> int:
    ocupados = Sesion.objects.filter(
        fecha=fecha,
        hora=hora,
        estado__in=['PROGRAMADA', 'RECUPERAR', 'RECUPERADA'],
        pack__tipo__in=['BB_FULL', 'BB_SEMANAL'],
    ).count()
    return ConfiguracionGeneral.get('CAPACIDAD_BODY_BALANCE', 20) - ocupados


def generar_fechas_bb_full(fecha_inicio: date) -> list:
    """
    Genera pares (fecha, hora) para Mensualidad Full durante 4 semanas,
    usando los slots BDB activos de ConfiguracionHorario. Salta feriados.
    """
    dia_hora_bb = get_dia_hora_bdb()
    feriados    = feriados_punta_arenas()
    fechas      = []
    cursor      = fecha_inicio
    fin         = fecha_inicio + timedelta(weeks=4)

    while cursor < fin:
        if cursor.weekday() in dia_hora_bb and cursor not in feriados:
            hora = dia_hora_bb[cursor.weekday()]
            fechas.append((cursor, hora))
        cursor += timedelta(days=1)

    return fechas  # [(date, hora), ...]


# ─── Vistas ───────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(["GET", "POST"])
def reservar_body_balance(request):
    hoy       = date.today()
    slots_bb  = get_slots_bdb()
    dias_activos = {s['dia'] for s in slots_bb}

    # Nombres de días para el subtítulo, ej: "Martes · Jueves · Sábado"
    dias_nombres = ' · '.join(s['dia_nombre'] for s in slots_bb)

    # Para JS: lista de js_day activos (Full) y mapa key→js_day (Semanal)
    dias_js_full = [s['js_day'] for s in slots_bb]
    dias_js_map  = {s['key']: s['js_day'] for s in slots_bb}

    # Subtexto dinámico para Mensualidad Full, ej: "2 veces por semana · Mar + Sáb"
    veces     = len(slots_bb)
    veces_txt = f"{veces} {'vez' if veces == 1 else 'veces'} por semana"
    dias_corto = ' + '.join(s['dia_nombre'][:3] for s in slots_bb)
    full_sub  = f"{veces_txt} · {dias_corto}"

    import json
    from .models import feriados_punta_arenas
    feriados = feriados_punta_arenas()
    context = {
        'hoy':           hoy,
        'slots_bb':      slots_bb,
        'dias_nombres':  dias_nombres,
        'dias_js_full':  dias_js_full,
        'dias_js_map':   dias_js_map,
        'full_sub':      full_sub,
        'precio_full':   ConfiguracionPrecio.get('BB_FULL', 60_000),
        'precio_semanal': ConfiguracionPrecio.get('BB_SEMANAL', 15_000),
        'feriados_json': json.dumps([f.isoformat() for f in feriados]),
    }

    if request.method == 'POST':
        tipo      = request.POST.get('tipo')
        dia_key   = request.POST.get('dia_bb')   # ahora es str(dia) ej: '1', '3', '5'

        if tipo == 'BB_FULL':
            fecha_str = request.POST.get('fecha_full')
        else:
            fecha_str = request.POST.get('fecha_semanal')

        errores = []

        if tipo not in ('BB_FULL', 'BB_SEMANAL'):
            errores.append('Debes elegir Mensualidad Full o Clase Semanal.')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < hoy:
                    errores.append('La fecha no puede ser en el pasado.')
            except ValueError:
                errores.append('Fecha no válida.')
        else:
            errores.append('Debes elegir una fecha de inicio.')

        if not errores and fecha_inicio:
            if tipo == 'BB_FULL':
                if fecha_inicio.weekday() not in dias_activos:
                    errores.append(
                        f'Para Mensualidad Full la primera clase debe ser '
                        f'{dias_nombres}.'
                    )
            elif tipo == 'BB_SEMANAL':
                keys_validas = {s['key'] for s in slots_bb}
                if not dia_key or dia_key not in keys_validas:
                    errores.append('Debes elegir un día para tu clase semanal.')
                else:
                    dia_esperado = int(dia_key)
                    if fecha_inicio.weekday() != dia_esperado:
                        nombre_esp = NOMBRE_DIA_LARGO[dia_esperado]
                        errores.append(
                            f'Para esa clase la fecha debe ser un {nombre_esp}.'
                        )

        if errores:
            context.update({
                'errores':    errores,
                'sel_tipo':   tipo,
                'sel_fecha':  fecha_str,
                'sel_dia_bb': dia_key,
            })
            return render(request, 'reservas/reservar_body_balance.html', context)

        if tipo == 'BB_FULL':
            pares = generar_fechas_bb_full(fecha_inicio)
            # Chequeo de cupo — si alguna fecha está llena no hay continuidad
            sin_cupo = [(f, h) for f, h in pares if cupos_bb(f, h) < 1]
            if sin_cupo:
                fechas_str = ', '.join(fmt_fecha_bb(f) for f, _ in sin_cupo)
                errores.append(
                    f'No hay cupo para el mes completo y mantener continuidad. '
                    f'Sin cupo en: {fechas_str}. '
                    f'Puedes reservar una Clase Semanal en los días disponibles.'
                )
                context.update({
                    'errores':    errores,
                    'sel_tipo':   tipo,
                    'sel_fecha':  fecha_str,
                    'sel_dia_bb': dia_key,
                })
                return render(request, 'reservas/reservar_body_balance.html', context)

            precio = ConfiguracionPrecio.get('BB_FULL', 60_000)
            request.session['bb_borrador'] = {
                'tipo':         tipo,
                'fecha_inicio': fecha_inicio.isoformat(),
                'dia_bb':       None,
                'pares':        [[f.isoformat(), h] for f, h in pares],
                'precio':       precio,
            }
        else:
            dia_int = int(dia_key)
            hora    = get_dia_hora_bdb()[dia_int]
            precio  = ConfiguracionPrecio.get('BB_SEMANAL', 15_000)
            request.session['bb_borrador'] = {
                'tipo':         tipo,
                'fecha_inicio': fecha_inicio.isoformat(),
                'dia_bb':       dia_key,
                'pares':        [[fecha_inicio.isoformat(), hora]],
                'precio':       precio,
            }

        return redirect('reservar_body_balance_confirmar')

    return render(request, 'reservas/reservar_body_balance.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def reservar_body_balance_confirmar(request):
    borrador = request.session.get('bb_borrador')
    if not borrador:
        messages.warning(request, 'Sesión expirada. Inicia la reserva de nuevo.')
        return redirect('reservar_body_balance')

    pares  = [(date.fromisoformat(f), h) for f, h in borrador['pares']]
    tipo   = borrador['tipo']
    fechas = [f for f, h in pares]

    context = {
        'tipo':         tipo,
        'tipo_label':   'Mensualidad Full' if tipo == 'BB_FULL' else 'Clase Semanal',
        'fecha_inicio': fechas[0],
        'fecha_fin':    fechas[-1],
        'fechas':       [(i + 1, f, h, fmt_fecha_bb(f)) for i, (f, h) in enumerate(pares)],
        'precio':       borrador['precio'],
        'es_full':      tipo == 'BB_FULL',
    }

    if request.method == 'POST':
        hora_pack = None if tipo == 'BB_FULL' else pares[0][1]

        # ── Chequeo de cupo antes de crear el pack ────────────────────────
        sin_cupo = [(f, h) for f, h in pares if cupos_bb(f, h) < 1]
        if sin_cupo:
            fechas_str = ', '.join(fmt_fecha_bb(f) for f, _ in sin_cupo)
            messages.error(request, f'Sin cupo disponible en: {fechas_str}. Elige otra fecha.')
            return redirect('reservar_body_balance')

        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = tipo,
            hora         = hora_pack,
            fecha_inicio = fechas[0],
            fecha_fin    = fechas[-1],
            cantidad     = len(pares),
        )
        del request.session['bb_borrador']

        from .views_webpay import crear_transaccion
        return_url = request.build_absolute_uri('/pago/webpay/retorno/')
        data = crear_transaccion(pack, return_url)

        token = data.get('token')
        url   = data.get('url')

        if not token or not url:
            pack.delete()
            messages.error(request, 'Error al conectar con Webpay. Intenta de nuevo.')
            return redirect('reservar_body_balance')

        request.session['bb_pares']       = borrador['pares']
        request.session['webpay_pack_id'] = pack.pk

        # Respaldo en DB — por si la sesión se pierde (ej: browser in-app de Instagram)
        if tipo == 'BB_FULL':
            pack.pares_json = borrador['pares']
            pack.save(update_fields=['pares_json'])

        return render(request, 'reservas/webpay_redirect.html', {
            'url':   url,
            'token': token,
        })

    return render(request, 'reservas/reservar_body_balance_confirmar.html', context)
