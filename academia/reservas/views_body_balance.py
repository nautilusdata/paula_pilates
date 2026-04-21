from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from .models import Pack, Sesion, feriados_punta_arenas, ConfiguracionGeneral, ConfiguracionPrecio

HORARIOS_BB = {
    'MAR': {'dia': 1, 'hora': 20, 'label': 'Martes 20:00'},
    'JUE': {'dia': 3, 'hora': 20, 'label': 'Jueves 20:00'},
    'SAB': {'dia': 5, 'hora': 11, 'label': 'Sábado 11:00'},
}

# Mapa rápido weekday → hora para BB_FULL (Mar=20, Jue=20, Sáb=11)
DIA_HORA_BB = {h['dia']: h['hora'] for h in HORARIOS_BB.values()}

NOMBRE_DIA = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
MES_ES = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril', 5: 'mayo', 6: 'junio',
    7: 'julio', 8: 'agosto', 9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
}

def fmt_fecha_bb(d: date) -> str:
    return f"{NOMBRE_DIA[d.weekday()]} {d.day} {MES_ES[d.month]}"


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
    Genera los pares (fecha, hora) del mes completo para Mensualidad Full
    (Mar 20:00 + Jue 20:00 + Sáb 11:00) a partir de la fecha de inicio,
    hasta completar 4 semanas, saltando feriados.

    Retorna: list of (date, hora_int)
    """
    feriados = feriados_punta_arenas()
    fechas = []
    cursor = fecha_inicio
    fin = fecha_inicio + timedelta(weeks=4)

    while cursor < fin:
        if cursor.weekday() in DIA_HORA_BB and cursor not in feriados:
            hora = DIA_HORA_BB[cursor.weekday()]   # ← hora correcta por día
            fechas.append((cursor, hora))
        cursor += timedelta(days=1)

    return fechas  # [(date, hora), ...]


@login_required
@require_http_methods(["GET", "POST"])
def reservar_body_balance(request):
    hoy = date.today()

    context = {
        'hoy':            hoy,
        'horarios':       HORARIOS_BB,
        'precio_full':    ConfiguracionPrecio.get('BB_FULL', 60_000),
        'precio_semanal': ConfiguracionPrecio.get('BB_SEMANAL', 15_000),
    }

    if request.method == 'POST':
        tipo   = request.POST.get('tipo')
        dia_bb = request.POST.get('dia_bb')

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
                if fecha_inicio.weekday() not in [1, 3, 5]:
                    errores.append('Para Mensualidad Full la primera clase debe ser martes, jueves o sábado.')
            elif tipo == 'BB_SEMANAL':
                if not dia_bb or dia_bb not in HORARIOS_BB:
                    errores.append('Debes elegir un día para tu clase semanal.')
                else:
                    dia_esperado = HORARIOS_BB[dia_bb]['dia']
                    if fecha_inicio.weekday() != dia_esperado:
                        nombres = {'MAR': 'martes', 'JUE': 'jueves', 'SAB': 'sábado'}
                        errores.append(f'Para {HORARIOS_BB[dia_bb]["label"]} la fecha debe ser un {nombres[dia_bb]}.')

        if errores:
            context.update({
                'errores':    errores,
                'sel_tipo':   tipo,
                'sel_fecha':  fecha_str,
                'sel_dia_bb': dia_bb,
            })
            return render(request, 'reservas/reservar_body_balance.html', context)

        if tipo == 'BB_FULL':
            # pares = [(date, hora), ...]  — cada día con su hora correcta
            pares  = generar_fechas_bb_full(fecha_inicio)
            precio = ConfiguracionPrecio.get('BB_FULL', 60_000)
            # Guardamos en sesión como lista de [fecha_iso, hora]
            request.session['bb_borrador'] = {
                'tipo':         tipo,
                'fecha_inicio': fecha_inicio.isoformat(),
                'dia_bb':       None,
                'pares':        [[f.isoformat(), h] for f, h in pares],
                'precio':       precio,
            }
        else:
            hora   = HORARIOS_BB[dia_bb]['hora']
            precio = ConfiguracionPrecio.get('BB_SEMANAL', 15_000)
            request.session['bb_borrador'] = {
                'tipo':         tipo,
                'fecha_inicio': fecha_inicio.isoformat(),
                'dia_bb':       dia_bb,
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

    # Reconstruir pares (date, hora) — cada uno con su hora correcta
    pares  = [(date.fromisoformat(f), h) for f, h in borrador['pares']]
    tipo   = borrador['tipo']
    fechas = [f for f, h in pares]

    context = {
        'tipo':         tipo,
        'tipo_label':   'Mensualidad Full' if tipo == 'BB_FULL' else 'Clase Semanal',
        'fecha_inicio': fechas[0],
        'fecha_fin':    fechas[-1],
        # Ahora incluimos la hora correcta de cada sesión en el template
        'fechas':       [(i + 1, f, h, fmt_fecha_bb(f)) for i, (f, h) in enumerate(pares)],
        'precio':       borrador['precio'],
        'es_full':      tipo == 'BB_FULL',
    }

    if request.method == 'POST':
        # Para BB_FULL el campo hora del Pack queda en None (irrelevante;
        # las sesiones llevan su propia hora). Para BB_SEMANAL hay una sola hora.
        hora_pack = None if tipo == 'BB_FULL' else pares[0][1]

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

        # Guardamos los pares en sesión para que _activar_pack los use
        request.session['bb_pares'] = borrador['pares']
        request.session['webpay_pack_id'] = pack.pk

        return render(request, 'reservas/webpay_redirect.html', {
            'url':   url,
            'token': token,
        })

    return render(request, 'reservas/reservar_body_balance_confirmar.html', context)
