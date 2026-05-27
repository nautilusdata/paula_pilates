"""
views_reservar_pack10.py
Flujo de reserva para Pack 10, Pack Reducido, Clase Suelta,
Clase de Prueba y Clase Privada — Pilates Reformer.

Cambio principal: días libres — la alumna elige cualquier combinación
de días disponibles según ConfiguracionHorario, sin esquemas fijos.
"""

from datetime import date, datetime, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.core.exceptions import ValidationError

from .models import (
    Pack, Sesion,
    generar_fechas_pack, crear_sesiones_pack, feriados_punta_arenas,
    horas_disponibles_por_tipo, slots_disponibles_pl, ConfiguracionPrecio,
    detectar_overlap,
)


# ─── Constantes ───────────────────────────────────────────────────────────────

NOMBRE_DIA = {
    0: 'Lunes', 1: 'Martes', 2: 'Miércoles',
    3: 'Jueves', 4: 'Viernes', 5: 'Sábado'
}

NOMBRE_DIA_CORTO = {
    0: 'Lun', 1: 'Mar', 2: 'Mié',
    3: 'Jue', 4: 'Vie', 5: 'Sáb'
}

MES_ES = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril', 5: 'mayo', 6: 'junio',
    7: 'julio', 8: 'agosto', 9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
}

# Label visual para sábado — horas con minutos
HORA_LABEL_ESPECIAL = {
    (5, 12): '12:15',
    (5, 13): '13:30',
}


def fmt_fecha(d: date) -> str:
    return f"{NOMBRE_DIA_CORTO[d.weekday()]} {d.day} {MES_ES[d.month]}"


def hora_label(dia: int, hora: int) -> str:
    """Retorna label visual de hora — especial para sábado slots 12 y 13."""
    return HORA_LABEL_ESPECIAL.get((dia, hora), f'{hora:02d}:00')


# ─── Helpers ──────────────────────────────────────────────────────────────────

def _slots_disponibles(dias: list, horas: dict, fecha_inicio: date, cantidad: int = 10):
    """
    dias  = [0, 2, 5]  (weekdays elegidos)
    horas = {0: 9, 2: 10, 5: 11}
    Retorna (pares, sin_cupo)
    """
    pares    = generar_fechas_pack(fecha_inicio, dias, horas, cantidad)
    sin_cupo = [(f, h) for f, h in pares if Sesion.cupos_disponibles(f, h) < 1]
    return pares, sin_cupo


def _parse_dias_post(request) -> list:
    """Lee los días seleccionados del POST → [0, 2, 5]"""
    dias = []
    for i in range(6):  # 0=Lun...5=Sáb
        if request.POST.get(f'dia_{i}'):
            dias.append(i)
    return sorted(dias)


def _parse_horas_post(dias: list, request) -> dict:
    """Lee las horas del POST → {0: 9, 2: 10, 5: 11}"""
    horas = {}
    for dia in dias:
        h_str = request.POST.get(f'hora_dia_{dia}')
        if h_str and h_str.isdigit():
            horas[dia] = int(h_str)
    return horas


def _frecuencia_str(dias: list) -> str:
    """[0, 2, 5] → '0,2,5'"""
    return ','.join(str(d) for d in sorted(dias))


# ─── AJAX: slots disponibles por día ─────────────────────────────────────────

@login_required
def horas_disponibles_ajax(request):
    """
    GET ?dias=0,2,5  → devuelve horas disponibles para esos días
    GET ?fecha=2026-04-10 → devuelve horas para clase suelta en esa fecha
    """
    dias_str  = request.GET.get('dias')
    fecha_str = request.GET.get('fecha')

    # ── Modo pack: horas por días elegidos ───────────────────────────────────
    if dias_str:
        try:
            dias = [int(d) for d in dias_str.split(',') if d.strip().isdigit()]
        except ValueError:
            return JsonResponse({'error': 'Días inválidos'}, status=400)

        resultado = []
        for dia in dias:
            horas = horas_disponibles_por_tipo('PL', dia=dia)
            resultado.append({
                'dia':    dia,
                'nombre': NOMBRE_DIA[dia],
                'horas':  [{'hora': h, 'label': hora_label(dia, h)} for h in horas],
            })
        return JsonResponse({'modo': 'pack', 'dias': resultado})

    # ── Modo suelta: horas para fecha concreta ────────────────────────────────
    if fecha_str:
        try:
            fecha = date.fromisoformat(fecha_str)
        except ValueError:
            return JsonResponse({'error': 'Fecha inválida'}, status=400)

        result = []
        for h in horas_disponibles_por_tipo('PL'):
            cupo = Sesion.cupos_disponibles(fecha, h)
            result.append({
                'hora':       h,
                'label':      hora_label(fecha.weekday(), h),
                'disponible': cupo > 0,
                'cupos_min':  cupo,
            })
        return JsonResponse({'modo': 'suelta', 'horas': result})

    return JsonResponse({'error': 'Parámetros inválidos'}, status=400)


# ─── AJAX: días disponibles ───────────────────────────────────────────────────

@login_required
def dias_disponibles_ajax(request):
    """
    GET → devuelve todos los días con slots PL activos.
    Usado por el selector de días en la reserva.
    """
    slots = slots_disponibles_pl()  # {dia: [hora, hora, ...]}
    resultado = []
    for dia in sorted(slots.keys()):
        resultado.append({
            'dia':    dia,
            'nombre': NOMBRE_DIA[dia],
            'horas':  [{'hora': h, 'label': hora_label(dia, h)} for h in slots[dia]],
        })
    return JsonResponse({'dias': resultado})


# ─── PACK 10 ──────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(["GET", "POST"])
def reservar_pack10(request):
    slots   = slots_disponibles_pl()  # {dia: [horas]}
    dias_disponibles = [
        {
            'dia':    dia,
            'nombre': NOMBRE_DIA[dia],
            'horas':  [{'hora': h, 'label': hora_label(dia, h)} for h in horas],
        }
        for dia, horas in sorted(slots.items())
    ]

    context = {
        'dias_disponibles': dias_disponibles,
        'precio_total':     ConfiguracionPrecio.get('PACK10', 0),
        'precio_por_clase': ConfiguracionPrecio.get('PACK10', 0) // 10,
        'hoy':              date.today(),
    }

    error_previo = request.session.pop('reserva_error', None)
    if error_previo:
        context['errores'] = [error_previo]

    if request.method == 'POST':
        dias      = _parse_dias_post(request)
        horas     = _parse_horas_post(dias, request)
        fecha_str = request.POST.get('fecha_inicio')

        errores = []

        if not dias:
            errores.append('Selecciona al menos un día.')
        elif len(dias) > 4:
            errores.append('Puedes elegir máximo 4 días por semana.')

        if dias and len(horas) < len(dias):
            errores.append('Selecciona la hora para cada día elegido.')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < date.today():
                    errores.append('La fecha de inicio no puede ser en el pasado.')
                elif dias and fecha_inicio.weekday() not in dias:
                    nombres = ', '.join(NOMBRE_DIA[d] for d in dias)
                    errores.append(f'La primera clase debe ser uno de los días elegidos: {nombres}.')
            except ValueError:
                errores.append('Fecha de inicio no válida.')
        else:
            errores.append('Selecciona la fecha de inicio.')

        pares    = []
        sin_cupo = []

        if not errores:
            try:
                pares, sin_cupo = _slots_disponibles(dias, horas, fecha_inicio, 10)
            except ValidationError as e:
                errores.extend(e.messages)

        if not errores and pares:
            colisiones = detectar_overlap(request.user, pares)
            if colisiones:
                dias_str = ', '.join(f"{fmt_fecha(f)} {h:02d}:00" for f, h in colisiones[:3])
                errores.append(f'Colisión de horarios en: {dias_str}. Elige otro horario.')

        if sin_cupo:
            dias_str = ', '.join(f"{fmt_fecha(f)} {h:02d}:00" for f, h in sin_cupo[:3])
            errores.append(f'Sin cupo disponible en: {dias_str}. Elige otro horario.')

        if errores:
            context.update({
                'errores':     errores,
                'sel_dias':    dias,
                'sel_horas':   horas,
                'sel_fecha':   fecha_str,
            })
            return render(request, 'reservas/reservar_pack10.html', context)

        # Guardar borrador con nuevo formato
        request.session['pack10_borrador'] = {
            'dias':         dias,
            'horas':        {str(k): v for k, v in horas.items()},
            'frecuencia':   _frecuencia_str(dias),
            'fecha_inicio': fecha_inicio.isoformat(),
            'pares':        [[f.isoformat(), h] for f, h in pares],
        }
        return redirect('reservar_pack10_confirmar')

    return render(request, 'reservas/reservar_pack10.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def reservar_pack10_confirmar(request):
    borrador = request.session.get('pack10_borrador')
    if not borrador:
        messages.warning(request, 'Sesión expirada. Inicia la reserva de nuevo.')
        return redirect('reservar_pack10')

    pares  = [(date.fromisoformat(f), h) for f, h in borrador['pares']]
    dias   = borrador['dias']
    horas  = {int(k): v for k, v in borrador['horas'].items()}

    horario_dias = [
        {'nombre': NOMBRE_DIA[d], 'hora': horas[d], 'label': hora_label(d, horas[d])}
        for d in dias
    ]

    context = {
        'frecuencia_label': ' · '.join(NOMBRE_DIA_CORTO[d] for d in dias),
        'fecha_inicio':     pares[0][0],
        'fecha_fin':        pares[-1][0],
        'sesiones':         [(i + 1, f, h, fmt_fecha(f)) for i, (f, h) in enumerate(pares)],
        'precio_total':     ConfiguracionPrecio.get('PACK10', 0),
        'precio_por_clase': ConfiguracionPrecio.get('PACK10', 0) // 10,
        'horario_dias':     horario_dias,
    }

    if request.method == 'POST':
        sin_cupo = [(f, h) for f, h in pares if Sesion.cupos_disponibles(f, h) < 1]
        if sin_cupo:
            request.session['reserva_error'] = 'Un horario se ocupó mientras confirmabas. Intenta de nuevo.'
            return redirect('reservar_pack10')

        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'PACK10',
            frecuencia   = borrador['frecuencia'],
            hora_dia1    = horas.get(dias[0]) if len(dias) > 0 else None,
            hora_dia2    = horas.get(dias[1]) if len(dias) > 1 else None,
            hora_dia3    = horas.get(dias[2]) if len(dias) > 2 else None,
            hora_dia4    = horas.get(dias[3]) if len(dias) > 3 else None,
            fecha_inicio = pares[0][0],
            cantidad     = 10,
        )
        del request.session['pack10_borrador']

        from .views_webpay import crear_transaccion
        return_url = request.build_absolute_uri('/pago/webpay/retorno/')
        data = crear_transaccion(pack, return_url)

        token = data.get('token')
        url   = data.get('url')

        if not token or not url:
            pack.delete()
            request.session['reserva_error'] = 'Error al conectar con Webpay. Intenta de nuevo.'
            return redirect('reservar_pack10')

        request.session['webpay_pack_id'] = pack.pk
        return render(request, 'reservas/webpay_redirect.html', {'url': url, 'token': token})

    return render(request, 'reservas/reservar_pack10_confirmar.html', context)


# ─── PACK REDUCIDO ────────────────────────────────────────────────────────────

@login_required
@require_http_methods(["GET", "POST"])
def reservar_pack_reducido(request):
    slots = slots_disponibles_pl()
    dias_disponibles = [
        {
            'dia':    dia,
            'nombre': NOMBRE_DIA[dia],
            'horas':  [{'hora': h, 'label': hora_label(dia, h)} for h in horas],
        }
        for dia, horas in sorted(slots.items())
    ]

    context = {
        'dias_disponibles': dias_disponibles,
        'precio_por_clase': ConfiguracionPrecio.get('PACK_REDUCIDO_CLASE', 20_000),
        'cantidades':       range(2, 10),
        'hoy':              date.today(),
    }

    error_previo = request.session.pop('reserva_error', None)
    if error_previo:
        context['errores'] = [error_previo]

    if request.method == 'POST':
        dias         = _parse_dias_post(request)
        horas        = _parse_horas_post(dias, request)
        fecha_str    = request.POST.get('fecha_inicio')
        cantidad_str = request.POST.get('cantidad')

        errores = []

        if not dias:
            errores.append('Selecciona al menos un día.')
        elif len(dias) > 4:
            errores.append('Puedes elegir máximo 4 días por semana.')

        if dias and len(horas) < len(dias):
            errores.append('Selecciona la hora para cada día elegido.')

        cantidad = int(cantidad_str) if cantidad_str and cantidad_str.isdigit() else None
        if not cantidad or not (2 <= cantidad <= 9):
            errores.append('La cantidad debe ser entre 2 y 9 clases.')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < date.today():
                    errores.append('La fecha no puede ser en el pasado.')
                elif dias and fecha_inicio.weekday() not in dias:
                    nombres = ', '.join(NOMBRE_DIA[d] for d in dias)
                    errores.append(f'La primera clase debe ser uno de los días elegidos: {nombres}.')
            except ValueError:
                errores.append('Fecha no válida.')
        else:
            errores.append('Selecciona la fecha de inicio.')

        pares    = []
        sin_cupo = []

        if not errores:
            try:
                pares, sin_cupo = _slots_disponibles(dias, horas, fecha_inicio, cantidad)
            except ValidationError as e:
                errores.extend(e.messages)

        if not errores and pares:
            colisiones = detectar_overlap(request.user, pares)
            if colisiones:
                dias_str = ', '.join(f"{fmt_fecha(f)} {h:02d}:00" for f, h in colisiones[:3])
                errores.append(f'Colisión de horarios en: {dias_str}. Elige otro horario.')

        if sin_cupo:
            dias_str = ', '.join(f"{fmt_fecha(f)} {h:02d}:00" for f, h in sin_cupo[:3])
            errores.append(f'Sin cupo en: {dias_str}')

        if errores:
            context.update({
                'errores':   errores,
                'sel_dias':  dias,
                'sel_horas': horas,
                'sel_fecha': fecha_str,
                'sel_cantidad': cantidad_str,
            })
            return render(request, 'reservas/reservar_pack_reducido.html', context)

        request.session['pack_reducido_borrador'] = {
            'dias':         dias,
            'horas':        {str(k): v for k, v in horas.items()},
            'frecuencia':   _frecuencia_str(dias),
            'fecha_inicio': fecha_inicio.isoformat(),
            'cantidad':     cantidad,
            'pares':        [[f.isoformat(), h] for f, h in pares],
        }
        return redirect('reservar_pack_reducido_confirmar')

    return render(request, 'reservas/reservar_pack_reducido.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def reservar_pack_reducido_confirmar(request):
    borrador = request.session.get('pack_reducido_borrador')
    if not borrador:
        messages.warning(request, 'Sesión expirada.')
        return redirect('reservar_pack_reducido')

    pares    = [(date.fromisoformat(f), h) for f, h in borrador['pares']]
    dias     = borrador['dias']
    horas    = {int(k): v for k, v in borrador['horas'].items()}
    cantidad = borrador['cantidad']
    precio   = cantidad * ConfiguracionPrecio.get('PACK_REDUCIDO_CLASE', 20_000)

    horario_dias = [
        {'nombre': NOMBRE_DIA[d], 'hora': horas[d], 'label': hora_label(d, horas[d])}
        for d in dias
    ]

    context = {
        'frecuencia_label': ' · '.join(NOMBRE_DIA_CORTO[d] for d in dias),
        'fecha_inicio':     pares[0][0],
        'fecha_fin':        pares[-1][0],
        'sesiones':         [(i + 1, f, h, fmt_fecha(f)) for i, (f, h) in enumerate(pares)],
        'cantidad':         cantidad,
        'precio_total':     precio,
        'precio_por_clase': ConfiguracionPrecio.get('PACK_REDUCIDO_CLASE', 20_000),
        'horario_dias':     horario_dias,
    }

    if request.method == 'POST':
        sin_cupo = [(f, h) for f, h in pares if Sesion.cupos_disponibles(f, h) < 1]
        if sin_cupo:
            request.session['reserva_error'] = 'Un horario se ocupó mientras confirmabas. Intenta de nuevo.'
            return redirect('reservar_pack_reducido')

        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'REDUCIDO',
            frecuencia   = borrador['frecuencia'],
            hora_dia1    = horas.get(dias[0]) if len(dias) > 0 else None,
            hora_dia2    = horas.get(dias[1]) if len(dias) > 1 else None,
            hora_dia3    = horas.get(dias[2]) if len(dias) > 2 else None,
            hora_dia4    = horas.get(dias[3]) if len(dias) > 3 else None,
            fecha_inicio = pares[0][0],
            cantidad     = cantidad,
        )
        del request.session['pack_reducido_borrador']

        from .views_webpay import crear_transaccion
        return_url = request.build_absolute_uri('/pago/webpay/retorno/')
        data = crear_transaccion(pack, return_url)

        token = data.get('token')
        url   = data.get('url')

        if not token or not url:
            pack.delete()
            request.session['reserva_error'] = 'Error al conectar con Webpay. Intenta de nuevo.'
            return redirect('reservar_pack_reducido')

        request.session['webpay_pack_id'] = pack.pk
        return render(request, 'reservas/webpay_redirect.html', {'url': url, 'token': token})

    return render(request, 'reservas/reservar_pack_reducido_confirmar.html', context)


# ─── CLASE SUELTA ─────────────────────────────────────────────────────────────

@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_suelta(request):
    context = {
        'horas':  [{'valor': h, 'label': f'{h:02d}:00'} for h in horas_disponibles_por_tipo('PL')],
        'precio': ConfiguracionPrecio.get('CLASE_SUELTA', 25_000),
        'hoy':    date.today(),
    }

    error_previo = request.session.pop('reserva_error', None)
    if error_previo:
        context['errores'] = [error_previo]

    if request.method == 'POST':
        hora_str  = request.POST.get('hora')
        fecha_str = request.POST.get('fecha_inicio')

        errores = []
        hora = int(hora_str) if hora_str and hora_str.isdigit() else None
        if not hora_str:
            errores.append('Debes seleccionar una hora.')
        elif hora is None or hora not in horas_disponibles_por_tipo('PL'):
            errores.append('Hora no válida.')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < date.today():
                    errores.append('La fecha no puede ser en el pasado.')
                elif fecha_inicio == date.today() and hora is not None:
                    if hora <= datetime.now().hour:
                        errores.append('Esa hora ya pasó hoy. Elige una hora futura.')
            except ValueError:
                errores.append('Fecha no válida.')
        else:
            errores.append('Selecciona una fecha.')

        if not errores:
            cupo = Sesion.cupos_disponibles(fecha_inicio, hora)
            if cupo < 1:
                errores.append('No hay cupo disponible en ese horario.')

        if errores:
            context.update({'errores': errores, 'sel_hora': hora_str, 'sel_fecha': fecha_str})
            return render(request, 'reservas/reservar_clase_suelta.html', context)

        request.session['clase_suelta_borrador'] = {
            'hora':         hora,
            'fecha_inicio': fecha_inicio.isoformat(),
        }
        return redirect('reservar_clase_suelta_confirmar')

    return render(request, 'reservas/reservar_clase_suelta.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_suelta_confirmar(request):
    borrador = request.session.get('clase_suelta_borrador')
    if not borrador:
        messages.warning(request, 'Sesión expirada.')
        return redirect('reservar_clase_suelta')

    fecha = date.fromisoformat(borrador['fecha_inicio'])
    context = {
        'hora':        borrador['hora'],
        'fecha':       fecha,
        'fecha_label': fmt_fecha(fecha),
        'precio':      ConfiguracionPrecio.get('CLASE_SUELTA', 25_000),
    }

    if request.method == 'POST':
        if Sesion.cupos_disponibles(fecha, borrador['hora']) < 1:
            request.session['reserva_error'] = 'El cupo se ocupó mientras confirmabas. Elige otro horario.'
            return redirect('reservar_clase_suelta')

        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'SUELTA',
            hora         = borrador['hora'],
            fecha_inicio = fecha,
            cantidad     = 1,
        )
        del request.session['clase_suelta_borrador']

        from .views_webpay import crear_transaccion
        return_url = request.build_absolute_uri('/pago/webpay/retorno/')
        data = crear_transaccion(pack, return_url)

        token = data.get('token')
        url   = data.get('url')

        if not token or not url:
            pack.delete()
            request.session['reserva_error'] = 'Error al conectar con Webpay. Intenta de nuevo.'
            return redirect('reservar_clase_suelta')

        request.session['webpay_pack_id'] = pack.pk
        return render(request, 'reservas/webpay_redirect.html', {'url': url, 'token': token})

    return render(request, 'reservas/reservar_clase_suelta_confirmar.html', context)


# ─── CLASE DE PRUEBA ──────────────────────────────────────────────────────────

@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_prueba(request):
    context = {
        'horas':  [{'valor': h, 'label': f'{h:02d}:00'} for h in horas_disponibles_por_tipo('TEST')],
        'precio': ConfiguracionPrecio.get('CLASE_PRUEBA', 15_000),
        'hoy':    date.today(),
    }

    error_previo = request.session.pop('reserva_error', None)
    if error_previo:
        context['errores'] = [error_previo]

    if request.method == 'POST':
        fecha_str = request.POST.get('fecha_inicio')

        horas_test = horas_disponibles_por_tipo('TEST')
        hora = horas_test[0] if horas_test else None

        errores = []

        if not hora:
            errores.append('No hay horarios configurados para la clase de prueba.')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < date.today():
                    errores.append('La fecha no puede ser en el pasado.')
                elif fecha_inicio.weekday() != 5:
                    errores.append('La clase de prueba es solo los sábados.')
                elif fecha_inicio == date.today() and hora is not None:
                    if hora <= datetime.now().hour:
                        errores.append('Esa hora ya pasó hoy. Elige una fecha futura.')
            except ValueError:
                errores.append('Fecha no válida.')
        else:
            errores.append('Selecciona una fecha.')

        if not errores:
            cupo = Sesion.cupos_disponibles(fecha_inicio, hora)
            if cupo < 1:
                errores.append('No hay cupo disponible en ese horario.')

        if errores:
            context.update({'errores': errores, 'sel_fecha': fecha_str})
            return render(request, 'reservas/reservar_clase_prueba.html', context)

        request.session['clase_prueba_borrador'] = {
            'hora':         hora,
            'fecha_inicio': fecha_inicio.isoformat(),
        }
        return redirect('reservar_clase_prueba_confirmar')

    return render(request, 'reservas/reservar_clase_prueba.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_prueba_confirmar(request):
    borrador = request.session.get('clase_prueba_borrador')
    if not borrador:
        messages.warning(request, 'Sesión expirada.')
        return redirect('reservar_clase_prueba')

    fecha = date.fromisoformat(borrador['fecha_inicio'])
    context = {
        'hora':        borrador['hora'],
        'fecha':       fecha,
        'fecha_label': fmt_fecha(fecha),
        'precio':      ConfiguracionPrecio.get('CLASE_PRUEBA', 15_000),
        'duracion':    '60 min',
    }

    if request.method == 'POST':
        if Sesion.cupos_disponibles(fecha, borrador['hora']) < 1:
            request.session['reserva_error'] = 'El cupo se ocupó mientras confirmabas.'
            return redirect('reservar_clase_prueba')

        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'PRUEBA',
            hora         = borrador['hora'],
            fecha_inicio = fecha,
            cantidad     = 1,
        )
        del request.session['clase_prueba_borrador']

        from .views_webpay import crear_transaccion
        return_url = request.build_absolute_uri('/pago/webpay/retorno/')
        data = crear_transaccion(pack, return_url)

        token = data.get('token')
        url   = data.get('url')

        if not token or not url:
            pack.delete()
            request.session['reserva_error'] = 'Error al conectar con Webpay. Intenta de nuevo.'
            return redirect('reservar_clase_prueba')

        request.session['webpay_pack_id'] = pack.pk
        return render(request, 'reservas/webpay_redirect.html', {'url': url, 'token': token})

    return render(request, 'reservas/reservar_clase_prueba_confirmar.html', context)


# ─── CLASE PRIVADA ────────────────────────────────────────────────────────────

def slot_privado_disponible(fecha: date, hora: int) -> bool:
    return not Sesion.objects.filter(
        fecha=fecha,
        hora=hora,
        estado__in=['PROGRAMADA', 'RECUPERAR', 'RECUPERADA'],
        pack__tipo='PRIVADA',
    ).exists()


def slots_disponibles_pv() -> dict:
    """Retorna dict {dia: [hora, hora, ...]} con todos los slots PV activos."""
    from .models import ConfiguracionHorario
    qs = ConfiguracionHorario.objects.filter(tipo='PV', activo=True).order_by('dia', 'hora')
    resultado = {}
    for ch in qs:
        resultado.setdefault(ch.dia, []).append(ch.hora)
    return resultado


@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_privada(request):
    slots = slots_disponibles_pv()
    dias_disponibles = [
        {
            'dia':    dia,
            'nombre': NOMBRE_DIA[dia],
            'horas':  [{'hora': h, 'label': f'{h:02d}:00'} for h in horas],
        }
        for dia, horas in sorted(slots.items())
    ]

    context = {
        'hoy':              date.today(),
        'dias_disponibles': dias_disponibles,
        'precio_pack10':    ConfiguracionPrecio.get('PRIVADA_PACK10', 285_000),
        'precio_reducido':  ConfiguracionPrecio.get('PRIVADA_CLASE', 30_000),
    }

    error_previo = request.session.pop('reserva_error', None)
    if error_previo:
        context['errores'] = [error_previo]

    if request.method == 'POST':
        tipo         = request.POST.get('tipo')
        dias         = _parse_dias_post(request)
        fecha_str    = request.POST.get('fecha_inicio')
        cantidad_str = request.POST.get('cantidad', '10')

        # Hora por día — igual que Pack 10
        horas_dict = {}
        for dia in dias:
            h_str = request.POST.get(f'hora_dia_{dia}')
            if h_str and h_str.isdigit():
                horas_dict[dia] = int(h_str)

        errores = []

        if tipo not in ('PRIVADA10', 'PRIVADA_REDUCIDO'):
            errores.append('Debes elegir Pack 10 o Pack Reducido.')

        if not dias:
            errores.append('Selecciona al menos un día.')
        elif len(horas_dict) < len(dias):
            errores.append('Debes elegir una hora para cada día seleccionado.')

        cantidad = 10
        if tipo == 'PRIVADA_REDUCIDO':
            cantidad = int(cantidad_str) if cantidad_str and cantidad_str.isdigit() else None
            if not cantidad or not (2 <= cantidad <= 9):
                errores.append('El pack reducido debe tener entre 2 y 9 clases.')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < date.today():
                    errores.append('La fecha no puede ser en el pasado.')
                elif dias and fecha_inicio.weekday() not in dias:
                    nombres = ', '.join(NOMBRE_DIA[d] for d in dias)
                    errores.append(f'La fecha debe ser uno de los días elegidos: {nombres}.')
            except ValueError:
                errores.append('Fecha no válida.')
        else:
            errores.append('Debes elegir una fecha de inicio.')

        fechas = []
        if not errores and fecha_inicio and horas_dict and dias:
            try:
                fechas = generar_fechas_pack(fecha_inicio, dias, horas_dict, cantidad)
                sin_cupo = [(f, h) for f, h in fechas if not slot_privado_disponible(f, h)]
                if sin_cupo:
                    errores.append(
                        'Paula no está disponible en: '
                        + ', '.join(fmt_fecha(f) for f, _ in sin_cupo[:3])
                        + ('…' if len(sin_cupo) > 3 else '')
                    )
            except ValidationError as e:
                errores.extend(e.messages)

        if errores:
            context.update({
                'errores':      errores,
                'sel_tipo':     tipo,
                'sel_dias':     dias,
                'sel_horas':    horas_dict,
                'sel_fecha':    fecha_str,
                'sel_cantidad': cantidad_str,
            })
            return render(request, 'reservas/reservar_clase_privada.html', context)

        precio = (ConfiguracionPrecio.get('PRIVADA_PACK10', 285_000) if tipo == 'PRIVADA10'
                  else cantidad * ConfiguracionPrecio.get('PRIVADA_CLASE', 30_000))

        fechas = generar_fechas_pack(fecha_inicio, dias, horas_dict, cantidad)

        request.session['privada_borrador'] = {
            'tipo':         tipo,
            'dias':         dias,
            'frecuencia':   _frecuencia_str(dias),
            'hora':         list(horas_dict.values())[0],  # hora representativa
            'fecha_inicio': fecha_inicio.isoformat(),
            'cantidad':     cantidad,
            'pares':        [[f.isoformat(), h] for f, h in fechas],
            'precio':       precio,
        }
        return redirect('reservar_clase_privada_confirmar')

    return render(request, 'reservas/reservar_clase_privada.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_privada_confirmar(request):
    borrador = request.session.get('privada_borrador')
    if not borrador:
        messages.warning(request, 'Sesión expirada.')
        return redirect('reservar_clase_privada')

    pares    = [(date.fromisoformat(f), h) for f, h in borrador['pares']]
    cantidad = borrador['cantidad']
    tipo     = borrador['tipo']
    dias     = borrador['dias']

    context = {
        'tipo_label':       'Pack 10 Clases Privadas' if tipo == 'PRIVADA10' else f'Pack {cantidad} Clases Privadas',
        'frecuencia_label': ' · '.join(NOMBRE_DIA_CORTO[d] for d in dias),
        'hora':             borrador['hora'],
        'fecha_inicio':     pares[0][0],
        'fecha_fin':        pares[-1][0],
        'sesiones':         [(i + 1, f, h, fmt_fecha(f)) for i, (f, h) in enumerate(pares)],
        'cantidad':         cantidad,
        'precio':           borrador['precio'],
        'precio_por_clase': (ConfiguracionPrecio.get('PRIVADA_PACK10', 285_000) // 10
                             if tipo == 'PRIVADA10'
                             else ConfiguracionPrecio.get('PRIVADA_CLASE', 30_000)),
    }

    if request.method == 'POST':
        sin_cupo = [(f, h) for f, h in pares if not slot_privado_disponible(f, h)]
        if sin_cupo:
            request.session['reserva_error'] = 'Un horario se ocupó mientras confirmabas. Intenta de nuevo.'
            return redirect('reservar_clase_privada')

        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'PRIVADA',
            frecuencia   = borrador['frecuencia'],
            hora         = borrador['hora'],
            fecha_inicio = pares[0][0],
            cantidad     = cantidad,
        )
        del request.session['privada_borrador']

        from .views_webpay import crear_transaccion
        return_url = request.build_absolute_uri('/pago/webpay/retorno/')
        data = crear_transaccion(pack, return_url)

        token = data.get('token')
        url   = data.get('url')

        if not token or not url:
            pack.delete()
            request.session['reserva_error'] = 'Error al conectar con Webpay. Intenta de nuevo.'
            return redirect('reservar_clase_privada')

        request.session['webpay_pack_id'] = pack.pk
        return render(request, 'reservas/webpay_redirect.html', {'url': url, 'token': token})

    return render(request, 'reservas/reservar_clase_privada_confirmar.html', context)
