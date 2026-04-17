"""
views_reservar_pack10.py
Flujo de reserva para Pack 10, Pack Reducido, Clase Suelta,
Clase de Prueba y Clase Privada — Pilates Reformer.

Cambio principal: PACK10 y REDUCIDO ahora piden una hora
distinta por cada día de la frecuencia (hora_dia1, hora_dia2, hora_dia3).
"""

from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.core.exceptions import ValidationError

from .models import (
    Pack, Sesion, DIAS_SEMANA_PILATES,
    generar_fechas_pack, crear_sesiones_pack, feriados_punta_arenas,
    horas_disponibles_por_tipo, ConfiguracionPrecio
)


# ─── Constantes ───────────────────────────────────────────────────────────────

NOMBRE_DIA = {0: 'Lunes', 1: 'Martes', 2: 'Miércoles', 3: 'Jueves', 4: 'Viernes'}

MES_ES = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril', 5: 'mayo', 6: 'junio',
    7: 'julio', 8: 'agosto', 9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
}

NOMBRE_DIA_CORTO = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie'}

NOMBRES_FRECUENCIA = {
    'LM':  'lunes o miércoles',
    'MJ':  'martes o jueves',
}

LABEL_FRECUENCIA = {
    'LMV': 'Lun · Miérc · Vier',
    'LM':  'Lun · Miérc',
    'MJ':  'Mar · Jue',
}


def fmt_fecha(d: date) -> str:
    return f"{NOMBRE_DIA_CORTO[d.weekday()]} {d.day} {MES_ES[d.month]}"


# ─── Helper: slots disponibles con horas por día ──────────────────────────────

def _slots_disponibles(frecuencia: str, horas: dict, fecha_inicio: date, cantidad: int = 10):
    """
    horas = {dia_semana: hora}  ej: {0: 9, 2: 10, 4: 8}
    Retorna (pares, sin_cupo)
      pares    = [(date, hora), ...]
      sin_cupo = [(date, hora), ...]  — slots sin cupo
    """
    pares = generar_fechas_pack(fecha_inicio, frecuencia, horas, cantidad)
    sin_cupo = [(f, h) for f, h in pares if Sesion.cupos_disponibles(f, h) < 1]
    return pares, sin_cupo


def _horas_dict_desde_post(frecuencia, hora_dia1, hora_dia2, hora_dia3):
    """Construye el dict {dia_semana: hora} desde los POST params."""
    dias = DIAS_SEMANA_PILATES[frecuencia]
    horas = {
        dias[0]: hora_dia1,
        dias[1]: hora_dia2,
    }
    if len(dias) == 3 and hora_dia3 is not None:
        horas[dias[2]] = hora_dia3
    return horas


# ─── AJAX: horas disponibles por día de frecuencia ───────────────────────────

@login_required
def horas_disponibles_ajax(request):
    """
    Para packs (PACK10, REDUCIDO):
      GET ?frecuencia=LMV  → devuelve horas disponibles por cada día de la frecuencia

    Para clase suelta:
      GET ?fecha=2026-04-10  → devuelve horas disponibles para esa fecha
    """
    frecuencia = request.GET.get('frecuencia')
    fecha_str  = request.GET.get('fecha')

    # ── Modo pack: horas por día ──────────────────────────────────────────────
    if frecuencia in DIAS_SEMANA_PILATES:
        dias = DIAS_SEMANA_PILATES[frecuencia]
        resultado = []
        for dia in dias:
            horas = horas_disponibles_por_tipo('PL', dia=dia)
            resultado.append({
                'dia':    dia,
                'nombre': NOMBRE_DIA[dia],
                'horas':  [{'hora': h, 'label': f'{h:02d}:00'} for h in horas],
            })
        return JsonResponse({'modo': 'pack', 'dias': resultado})

    # ── Modo suelta: horas para una fecha concreta ────────────────────────────
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
                'label':      f'{h:02d}:00',
                'disponible': cupo > 0,
                'cupos_min':  cupo,
            })
        return JsonResponse({'modo': 'suelta', 'horas': result})

    return JsonResponse({'error': 'Parámetros inválidos'}, status=400)


# ─── PACK 10 ──────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(["GET", "POST"])
def reservar_pack10(request):
    context = {
        'frecuencias': [
            {'codigo': 'LMV', 'label': 'Lun · Miérc · Vier', 'dias': '3 días/semana'},
            {'codigo': 'LM',  'label': 'Lun · Miérc',         'dias': '2 días/semana'},
            {'codigo': 'MJ',  'label': 'Mar · Jue',            'dias': '2 días/semana'},
        ],
        'precio_total':     ConfiguracionPrecio.get('PACK10', 0),
        'precio_por_clase': ConfiguracionPrecio.get('PACK10', 0) // 10,
        'hoy':              date.today(),
    }

    if request.method == 'POST':
        frecuencia   = request.POST.get('frecuencia')
        fecha_str    = request.POST.get('fecha_inicio')
        hora1_str    = request.POST.get('hora_dia1')
        hora2_str    = request.POST.get('hora_dia2')
        hora3_str    = request.POST.get('hora_dia3')

        errores = []

        if frecuencia not in DIAS_SEMANA_PILATES:
            errores.append('Selecciona una frecuencia válida.')

        def parse_hora(s, label):
            if not s or not s.isdigit():
                errores.append(f'Selecciona la hora del {label}.')
                return None
            return int(s)

        hora_dia1 = parse_hora(hora1_str, 'primer día')
        hora_dia2 = parse_hora(hora2_str, 'segundo día')
        hora_dia3 = None
        if frecuencia == 'LMV':
            hora_dia3 = parse_hora(hora3_str, 'viernes')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < date.today():
                    errores.append('La fecha de inicio no puede ser en el pasado.')
                elif frecuencia in DIAS_SEMANA_PILATES:
                    dias = DIAS_SEMANA_PILATES[frecuencia]
                    if fecha_inicio.weekday() not in dias:
                        errores.append(
                            f'Para {frecuencia}, la primera clase debe ser un {NOMBRES_FRECUENCIA[frecuencia]}.'
                        )
            except ValueError:
                errores.append('Fecha de inicio no válida.')
        else:
            errores.append('Selecciona la fecha de inicio.')

        if not errores:
            pares = []
            sin_cupo = []
            try:
                horas = _horas_dict_desde_post(frecuencia, hora_dia1, hora_dia2, hora_dia3)
                pares, sin_cupo = _slots_disponibles(frecuencia, horas, fecha_inicio)
            except ValidationError as e:
                errores.extend(e.messages)

            if sin_cupo:
                dias_str = ', '.join(
                    f"{fmt_fecha(f)} {h:02d}:00" for f, h in sin_cupo[:3]
                )
                errores.append(
                    f'Sin cupo disponible en: {dias_str}'
                    + ('…' if len(sin_cupo) > 3 else '')
                    + '. Elige otro horario.'
                )

        if errores:
            context.update({
                'errores':        errores,
                'sel_frecuencia': frecuencia,
                'sel_fecha':      fecha_str,
                'sel_hora_dia1':  hora1_str,
                'sel_hora_dia2':  hora2_str,
                'sel_hora_dia3':  hora3_str,
            })
            return render(request, 'reservas/reservar_pack10.html', context)

        request.session['pack10_borrador'] = {
            'frecuencia':   frecuencia,
            'hora_dia1':    hora_dia1,
            'hora_dia2':    hora_dia2,
            'hora_dia3':    hora_dia3,
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

    pares = [(date.fromisoformat(f), h) for f, h in borrador['pares']]
    frecuencia = borrador['frecuencia']
    dias = DIAS_SEMANA_PILATES[frecuencia]

    context = {
        'frecuencia_label': LABEL_FRECUENCIA[frecuencia],
        'fecha_inicio':     pares[0][0],
        'fecha_fin':        pares[-1][0],
        'sesiones':         [(i + 1, f, h, fmt_fecha(f)) for i, (f, h) in enumerate(pares)],
        'precio_total':     ConfiguracionPrecio.get('PACK10', 0),
        'precio_por_clase': ConfiguracionPrecio.get('PACK10', 0) // 10,
        # Resumen de horario por día
        'horario_dias': [
            {'nombre': NOMBRE_DIA[dias[0]], 'hora': borrador['hora_dia1']},
            {'nombre': NOMBRE_DIA[dias[1]], 'hora': borrador['hora_dia2']},
        ] + ([{'nombre': NOMBRE_DIA[dias[2]], 'hora': borrador['hora_dia3']}]
             if len(dias) == 3 else []),
    }

    if request.method == 'POST':
        # Re-verificar cupos al momento de confirmar
        sin_cupo = [(f, h) for f, h in pares if Sesion.cupos_disponibles(f, h) < 1]
        if sin_cupo:
            messages.error(request, 'Un horario se ocupó mientras confirmabas. Intenta de nuevo.')
            return redirect('reservar_pack10')

        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'PACK10',
            frecuencia   = frecuencia,
            hora_dia1    = borrador['hora_dia1'],
            hora_dia2    = borrador['hora_dia2'],
            hora_dia3    = borrador.get('hora_dia3'),
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
            messages.error(request, 'Error al conectar con Webpay. Intenta de nuevo.')
            return redirect('reservar_pack10')

        request.session['webpay_pack_id'] = pack.pk
        return render(request, 'reservas/webpay_redirect.html', {'url': url, 'token': token})

    return render(request, 'reservas/reservar_pack10_confirmar.html', context)


# ─── PACK REDUCIDO ────────────────────────────────────────────────────────────

@login_required
@require_http_methods(["GET", "POST"])
def reservar_pack_reducido(request):
    context = {
        'frecuencias': [
            {'codigo': 'LMV', 'label': 'Lun · Miérc · Vier', 'dias': '3 días/semana'},
            {'codigo': 'LM',  'label': 'Lun · Miérc',         'dias': '2 días/semana'},
            {'codigo': 'MJ',  'label': 'Mar · Jue',            'dias': '2 días/semana'},
        ],
        'precio_por_clase': ConfiguracionPrecio.get('PACK_REDUCIDO_CLASE', 20_000),
        'cantidades':       range(2, 10),
        'hoy':              date.today(),
    }

    if request.method == 'POST':
        frecuencia   = request.POST.get('frecuencia')
        fecha_str    = request.POST.get('fecha_inicio')
        cantidad_str = request.POST.get('cantidad')
        hora1_str    = request.POST.get('hora_dia1')
        hora2_str    = request.POST.get('hora_dia2')
        hora3_str    = request.POST.get('hora_dia3')

        errores = []

        if frecuencia not in DIAS_SEMANA_PILATES:
            errores.append('Selecciona una frecuencia válida.')

        cantidad = int(cantidad_str) if cantidad_str and cantidad_str.isdigit() else None
        if not cantidad or not (2 <= cantidad <= 9):
            errores.append('La cantidad debe ser entre 2 y 9 clases.')

        def parse_hora(s, label):
            if not s or not s.isdigit():
                errores.append(f'Selecciona la hora del {label}.')
                return None
            return int(s)

        hora_dia1 = parse_hora(hora1_str, 'primer día')
        hora_dia2 = parse_hora(hora2_str, 'segundo día')
        hora_dia3 = None
        if frecuencia == 'LMV':
            hora_dia3 = parse_hora(hora3_str, 'viernes')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < date.today():
                    errores.append('La fecha no puede ser en el pasado.')
                elif frecuencia in DIAS_SEMANA_PILATES:
                    if fecha_inicio.weekday() not in DIAS_SEMANA_PILATES[frecuencia]:
                        errores.append(
                            f'Para {frecuencia}, la primera clase debe ser un {NOMBRES_FRECUENCIA[frecuencia]}.'
                        )
            except ValueError:
                errores.append('Fecha no válida.')
        else:
            errores.append('Selecciona la fecha de inicio.')

        if not errores:
            pares = []
            sin_cupo = []
            try:
                horas = _horas_dict_desde_post(frecuencia, hora_dia1, hora_dia2, hora_dia3)
                pares, sin_cupo = _slots_disponibles(frecuencia, horas, fecha_inicio, cantidad)
            except ValidationError as e:
                errores.extend(e.messages)

            if sin_cupo:
                dias_str = ', '.join(f"{fmt_fecha(f)} {h:02d}:00" for f, h in sin_cupo[:3])
                errores.append(
                    f'Sin cupo en: {dias_str}' + ('…' if len(sin_cupo) > 3 else '')
                )

        if errores:
            context.update({
                'errores':        errores,
                'sel_frecuencia': frecuencia,
                'sel_fecha':      fecha_str,
                'sel_cantidad':   cantidad_str,
                'sel_hora_dia1':  hora1_str,
                'sel_hora_dia2':  hora2_str,
                'sel_hora_dia3':  hora3_str,
            })
            return render(request, 'reservas/reservar_pack_reducido.html', context)

        request.session['pack_reducido_borrador'] = {
            'frecuencia':   frecuencia,
            'hora_dia1':    hora_dia1,
            'hora_dia2':    hora_dia2,
            'hora_dia3':    hora_dia3,
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
        messages.warning(request, 'Sesión expirada. Inicia la reserva de nuevo.')
        return redirect('reservar_pack_reducido')

    pares    = [(date.fromisoformat(f), h) for f, h in borrador['pares']]
    cantidad = borrador['cantidad']
    precio   = cantidad * ConfiguracionPrecio.get('PACK_REDUCIDO_CLASE', 20_000)
    frecuencia = borrador['frecuencia']
    dias = DIAS_SEMANA_PILATES[frecuencia]

    context = {
        'frecuencia_label': LABEL_FRECUENCIA[frecuencia],
        'fecha_inicio':     pares[0][0],
        'fecha_fin':        pares[-1][0],
        'sesiones':         [(i + 1, f, h, fmt_fecha(f)) for i, (f, h) in enumerate(pares)],
        'cantidad':         cantidad,
        'precio_total':     precio,
        'precio_por_clase': ConfiguracionPrecio.get('PACK_REDUCIDO_CLASE', 20_000),
        'horario_dias': [
            {'nombre': NOMBRE_DIA[dias[0]], 'hora': borrador['hora_dia1']},
            {'nombre': NOMBRE_DIA[dias[1]], 'hora': borrador['hora_dia2']},
        ] + ([{'nombre': NOMBRE_DIA[dias[2]], 'hora': borrador['hora_dia3']}]
             if len(dias) == 3 else []),
    }

    if request.method == 'POST':
        sin_cupo = [(f, h) for f, h in pares if Sesion.cupos_disponibles(f, h) < 1]
        if sin_cupo:
            messages.error(request, 'Un horario se ocupó mientras confirmabas. Intenta de nuevo.')
            return redirect('reservar_pack_reducido')

        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'REDUCIDO',
            frecuencia   = frecuencia,
            hora_dia1    = borrador['hora_dia1'],
            hora_dia2    = borrador['hora_dia2'],
            hora_dia3    = borrador.get('hora_dia3'),
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
            messages.error(request, 'Error al conectar con Webpay. Intenta de nuevo.')
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

    if request.method == 'POST':
        hora_str  = request.POST.get('hora')
        fecha_str = request.POST.get('fecha_inicio')

        errores = []
        hora = int(hora_str) if hora_str and hora_str.isdigit() else None
        if not hora or hora not in horas_disponibles_por_tipo('PL'):
            errores.append('Hora no válida.')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < date.today():
                    errores.append('La fecha no puede ser en el pasado.')
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
            messages.error(request, 'El cupo se ocupó mientras confirmabas. Elige otro horario.')
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
            messages.error(request, 'Error al conectar con Webpay. Intenta de nuevo.')
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

    if request.method == 'POST':
        hora_str  = request.POST.get('hora')
        fecha_str = request.POST.get('fecha_inicio')

        errores = []
        hora = int(hora_str) if hora_str and hora_str.isdigit() else None
        if not hora or hora not in horas_disponibles_por_tipo('TEST'):
            errores.append('Hora no válida.')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < date.today():
                    errores.append('La fecha no puede ser en el pasado.')
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
    }

    if request.method == 'POST':
        if Sesion.cupos_disponibles(fecha, borrador['hora']) < 1:
            messages.error(request, 'El cupo se ocupó mientras confirmabas.')
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
            messages.error(request, 'Error al conectar con Webpay. Intenta de nuevo.')
            return redirect('reservar_clase_prueba')

        request.session['webpay_pack_id'] = pack.pk
        return render(request, 'reservas/webpay_redirect.html', {'url': url, 'token': token})

    return render(request, 'reservas/reservar_clase_prueba_confirmar.html', context)


# ─── CLASE PRIVADA ────────────────────────────────────────────────────────────

HORAS_PRIVADAS = [11, 16]


def slot_privado_disponible(fecha: date, hora: int) -> bool:
    return not Sesion.objects.filter(
        fecha=fecha,
        hora=hora,
        estado__in=['PROGRAMADA', 'RECUPERAR', 'RECUPERADA'],
    ).exists()


@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_privada(request):
    context = {
        'hoy':   date.today(),
        'horas': [{'valor': h, 'label': f'{h:02d}:00'} for h in HORAS_PRIVADAS],
        'frecuencias': [
            {'codigo': 'LM',  'label': 'Lun · Miérc', 'dias': '2 días/semana'},
            {'codigo': 'MJ',  'label': 'Mar · Jue',    'dias': '2 días/semana'},
        ],
        'precio_pack10':   ConfiguracionPrecio.get('PRIVADA_PACK10', 285_000),
        'precio_reducido': ConfiguracionPrecio.get('PRIVADA_CLASE', 30_000),
    }

    if request.method == 'POST':
        tipo         = request.POST.get('tipo')
        frecuencia   = request.POST.get('frecuencia')
        hora_str     = request.POST.get('hora')
        fecha_str    = request.POST.get('fecha_inicio')
        cantidad_str = request.POST.get('cantidad', '10')

        errores = []

        if tipo not in ('PRIVADA10', 'PRIVADA_REDUCIDO'):
            errores.append('Debes elegir Pack 10 o Pack Reducido.')
        if frecuencia not in DIAS_SEMANA_PILATES:
            errores.append('Frecuencia no válida.')

        hora = int(hora_str) if hora_str and hora_str.isdigit() else None
        if not hora or hora not in HORAS_PRIVADAS:
            errores.append('Hora no válida.')

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
                elif frecuencia and fecha_inicio.weekday() not in DIAS_SEMANA_PILATES.get(frecuencia, []):
                    errores.append(f'La fecha debe ser un {NOMBRES_FRECUENCIA.get(frecuencia, "")}.')
            except ValueError:
                errores.append('Fecha no válida.')
        else:
            errores.append('Debes elegir una fecha de inicio.')

        if not errores and fecha_inicio and hora and frecuencia:
            # Privada usa una sola hora para todos los días
            horas_dict = {d: hora for d in DIAS_SEMANA_PILATES[frecuencia]}
            fechas = generar_fechas_pack(fecha_inicio, frecuencia, horas_dict, cantidad)
            sin_cupo = [(f, h) for f, h in fechas if not slot_privado_disponible(f, h)]
            if sin_cupo:
                errores.append(
                    'Paula no está disponible en: '
                    + ', '.join(fmt_fecha(f) for f, _ in sin_cupo[:3])
                    + ('…' if len(sin_cupo) > 3 else '')
                )

        if errores:
            context.update({
                'errores':        errores,
                'sel_tipo':       tipo,
                'sel_frecuencia': frecuencia,
                'sel_hora':       hora_str,
                'sel_fecha':      fecha_str,
                'sel_cantidad':   cantidad_str,
            })
            return render(request, 'reservas/reservar_clase_privada.html', context)

        precio = (ConfiguracionPrecio.get('PRIVADA_PACK10', 285_000) if tipo == 'PRIVADA10'
                  else cantidad * ConfiguracionPrecio.get('PRIVADA_CLASE', 30_000))

        horas_dict = {d: hora for d in DIAS_SEMANA_PILATES[frecuencia]}
        fechas = generar_fechas_pack(fecha_inicio, frecuencia, horas_dict, cantidad)

        request.session['privada_borrador'] = {
            'tipo':         tipo,
            'frecuencia':   frecuencia,
            'hora':         hora,
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

    context = {
        'tipo_label':       'Pack 10 Clases Privadas' if tipo == 'PRIVADA10' else f'Pack {cantidad} Clases Privadas',
        'frecuencia_label': LABEL_FRECUENCIA[borrador['frecuencia']],
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
            messages.error(request, 'Un horario se ocupó mientras confirmabas. Intenta de nuevo.')
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
            messages.error(request, 'Error al conectar con Webpay. Intenta de nuevo.')
            return redirect('reservar_clase_privada')

        request.session['webpay_pack_id'] = pack.pk
        return render(request, 'reservas/webpay_redirect.html', {'url': url, 'token': token})

    return render(request, 'reservas/reservar_clase_privada_confirmar.html', context)
