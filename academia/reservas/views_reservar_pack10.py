"""
views_reservar_pack10.py
Flujo de reserva para Pack 10 Clases — Pilates Reformer.

Pasos:
  GET  /reservar/pack10/              → Paso 1: formulario de frecuencia + hora + fecha inicio
  POST /reservar/pack10/              → Valida y devuelve preview (JSON o redirect)
  GET  /reservar/pack10/confirmar/    → Paso 2: resumen antes de pagar
  POST /reservar/pack10/confirmar/    → Crea Pack en estado PENDIENTE_PAGO → redirige a WebPay

Integración futura con WebPay:
  - El webhook de Transbank llama a /reservar/pack10/webpay-callback/
  - Si pago OK → se llaman crear_sesiones_pack() y estado → ACTIVO
  - Si pago FALLA → Pack se elimina o queda CANCELADO
"""

from datetime import date, timedelta
from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.utils.timezone import now

from .models import (
    Pack, Sesion, DIAS_SEMANA_PILATES,
    generar_fechas_pack, crear_sesiones_pack, feriados_punta_arenas,
    horas_disponibles_por_tipo, ConfiguracionPrecio
)


# ─── Helpers de disponibilidad ────────────────────────────────────────────────

def _slots_disponibles(frecuencia: str, hora: int, fecha_inicio: date, cantidad: int = 10):
    """
    Dado una frecuencia y hora, calcula las N fechas del pack
    y devuelve disponibilidad cupo a cupo.
    Retorna (fechas_ok: list[date], fechas_sin_cupo: list[date])
    """
    fechas = generar_fechas_pack(fecha_inicio, frecuencia, cantidad)
    sin_cupo = [f for f in fechas if Sesion.cupos_disponibles(f, hora) < 1]
    return fechas, sin_cupo


def _proxima_fecha_valida(frecuencia: str) -> date:
    """
    Retorna la próxima fecha desde hoy que coincida con uno de los
    días de la frecuencia elegida (para sugerir fecha mínima en el picker).
    """
    dias = DIAS_SEMANA_PILATES[frecuencia]
    cursor = date.today()
    for _ in range(14):
        if cursor.weekday() in dias:
            return cursor
        cursor += timedelta(days=1)
    return date.today()


# ─── Nombres de día en español ────────────────────────────────────────────────

NOMBRE_DIA = {0: 'Lun', 1: 'Mar', 2: 'Mié', 3: 'Jue', 4: 'Vie', 5: 'Sáb', 6: 'Dom'}
MES_ES = {
    1: 'enero', 2: 'febrero', 3: 'marzo', 4: 'abril', 5: 'mayo', 6: 'junio',
    7: 'julio', 8: 'agosto', 9: 'septiembre', 10: 'octubre', 11: 'noviembre', 12: 'diciembre'
}

def fmt_fecha(d: date) -> str:
    return f"{NOMBRE_DIA[d.weekday()]} {d.day} {MES_ES[d.month]}"


# ─── Vistas ───────────────────────────────────────────────────────────────────

@login_required
@require_http_methods(["GET", "POST"])
def reservar_pack10(request):
    """
    Paso 1 y 2: El usuario elige frecuencia, hora y fecha de inicio.
    Si el formulario es válido, se guarda el borrador en session y
    se redirige a la vista de confirmación.
    """
    context = {
        'frecuencias': [
            {'codigo': 'LMV', 'label': 'Lun · Miérc · Vier', 'dias': '3 días/semana'},
            {'codigo': 'LM',  'label': 'Lun · Miérc',         'dias': '2 días/semana'},
            {'codigo': 'MJ',  'label': 'Mar · Jue',            'dias': '2 días/semana'},
        ],
        'horas': [
            {'valor': h, 'label': f'{h:02d}:00'}
            for h in horas_disponibles_por_tipo('PL')
        ],
        'precio_total': ConfiguracionPrecio.get('PACK10', 140_000),
        'precio_por_clase': 14_000,
    }

    if request.method == 'POST':
        frecuencia  = request.POST.get('frecuencia')
        hora_str    = request.POST.get('hora')
        fecha_str   = request.POST.get('fecha_inicio')

        # Validaciones básicas
        errores = []
        if frecuencia not in DIAS_SEMANA_PILATES:
            errores.append('Frecuencia no válida.')
        if hora_str and not hora_str.isdigit():
            errores.append('Hora no válida.')
        hora = int(hora_str) if hora_str and hora_str.isdigit() else None
        if hora and hora not in horas_disponibles_por_tipo('PL'):
            errores.append(f'La hora {hora}:00 no está disponible para Pilates.')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < date.today():
                    errores.append('La fecha de inicio no puede ser en el pasado.')
            except ValueError:
                errores.append('Fecha de inicio no válida.')

        if not errores and frecuencia and hora and fecha_inicio:
            # Verificar que la fecha coincida con la frecuencia
            dias = DIAS_SEMANA_PILATES[frecuencia]
            if fecha_inicio.weekday() not in dias:
                nombres = {
                    'LMV': 'lunes, miércoles o viernes',
                    'LM':  'lunes o miércoles',
                    'MJ':  'martes o jueves',
                }
                errores.append(
                    f'Para {frecuencia}, la primera clase debe ser un {nombres[frecuencia]}.'
                )

        if not errores:
            # Calcular las 10 fechas
            fechas, sin_cupo = _slots_disponibles(frecuencia, hora, fecha_inicio)

            if sin_cupo:
                errores.append(
                    f'Sin cupo disponible en {len(sin_cupo)} fecha(s): '
                    + ', '.join(fmt_fecha(f) for f in sin_cupo[:3])
                    + ('…' if len(sin_cupo) > 3 else '')
                    + '. Elige otra hora u otro día de inicio.'
                )

        if errores:
            context.update({'errores': errores,
                            'sel_frecuencia': frecuencia,
                            'sel_hora': hora_str,
                            'sel_fecha': fecha_str})
            return render(request, 'reservas/reservar_pack10.html', context)

        # Guardar borrador en sesión (no en DB todavía)
        request.session['pack10_borrador'] = {
            'frecuencia':   frecuencia,
            'hora':         hora,
            'fecha_inicio': fecha_inicio.isoformat(),
            'fechas':       [f.isoformat() for f in fechas],
        }
        return redirect('reservar_pack10_confirmar')

    return render(request, 'reservas/reservar_pack10.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def reservar_pack10_confirmar(request):
    """
    Paso 3: Muestra el resumen con las 10 fechas calculadas.
    POST: Crea el Pack (estado PENDIENTE_PAGO) y redirige a Webpay.
    """
    borrador = request.session.get('pack10_borrador')
    if not borrador:
        messages.warning(request, 'Sesión expirada. Inicia la reserva de nuevo.')
        return redirect('reservar_pack10')

    fechas = [date.fromisoformat(f) for f in borrador['fechas']]
    feriados = feriados_punta_arenas()
    feriados_en_pack = [f for f in fechas if f in feriados]

    context = {
        'frecuencia_label': {
            'LMV': 'Lun · Miérc · Vier',
            'LM':  'Lun · Miérc',
            'MJ':  'Mar · Jue',
        }[borrador['frecuencia']],
        'hora':             borrador['hora'],
        'fecha_inicio':     date.fromisoformat(borrador['fecha_inicio']),
        'fecha_fin':        fechas[-1],
        'fechas':           [(i + 1, f, fmt_fecha(f)) for i, f in enumerate(fechas)],
        'precio_total':     ConfiguracionPrecio.get('PACK10', 140_000),
        'precio_por_clase': 14_000,
    }

    if request.method == 'POST':
        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'PACK10',
            frecuencia   = borrador['frecuencia'],
            hora         = borrador['hora'],
            fecha_inicio = date.fromisoformat(borrador['fecha_inicio']),
            cantidad     = 10,
        )
        del request.session['pack10_borrador']

        from .views_webpay import crear_transaccion
        return_url = 'https://gabriela-nonacceleratory-nonelectrically.ngrok-free.dev/pago/webpay/retorno/'
        data = crear_transaccion(pack, return_url)

        token = data.get('token')
        url   = data.get('url')

        if not token or not url:
            pack.delete()
            messages.error(request, 'Error al conectar con Webpay. Intenta de nuevo.')
            return redirect('reservar_pack10')

        request.session['webpay_pack_id'] = pack.pk

        return render(request, 'reservas/webpay_redirect.html', {
            'url':   url,
            'token': token,
        })

    return render(request, 'reservas/reservar_pack10_confirmar.html', context)


# ─── AJAX: horas disponibles para una frecuencia + fecha ──────────────────────

@login_required
def horas_disponibles_ajax(request):
    """
    GET /reservar/pack10/horas-disponibles/?frecuencia=LMV&fecha=2026-04-06
    Devuelve JSON con disponibilidad de cada hora.
    """
    frecuencia  = request.GET.get('frecuencia')
    fecha_str   = request.GET.get('fecha')

    if not fecha_str:
        return JsonResponse({'error': 'Parámetros inválidos'}, status=400)

    try:
        fecha_inicio = date.fromisoformat(fecha_str)
    except ValueError:
        return JsonResponse({'error': 'Fecha inválida'}, status=400)

    result = []
    for h in horas_disponibles_por_tipo('PL'):
        if frecuencia not in DIAS_SEMANA_PILATES:
            # Clase suelta — solo chequea ese día
            cupo = Sesion.cupos_disponibles(fecha_inicio, h)
            result.append({
                'hora':       h,
                'label':      f'{h:02d}:00',
                'disponible': cupo > 0,
                'cupos_min':  cupo,
            })
        else:
            # Packs — proyecta todas las fechas
            cantidad = int(request.GET.get('cantidad', 10))
            fechas, sin_cupo = _slots_disponibles(frecuencia, h, fecha_inicio, cantidad)
            cupo_minimo = min(
                Sesion.cupos_disponibles(f, h) for f in fechas
            )
            result.append({
                'hora':       h,
                'label':      f'{h:02d}:00',
                'disponible': len(sin_cupo) == 0,
                'cupos_min':  cupo_minimo,
            })
    return JsonResponse({'horas': result})




# ─── RESERVAR PACK REDUCIDO (2 a 9 clases) ──────────────────────


@login_required
@require_http_methods(["GET", "POST"])
def reservar_pack_reducido(request):
    context = {
        'frecuencias': [
            {'codigo': 'LMV', 'label': 'Lun · Miérc · Vier', 'dias': '3 días/semana'},
            {'codigo': 'LM',  'label': 'Lun · Miérc',         'dias': '2 días/semana'},
            {'codigo': 'MJ',  'label': 'Mar · Jue',            'dias': '2 días/semana'},
        ],
        'horas': [{'valor': h, 'label': f'{h:02d}:00'} for h in horas_disponibles_por_tipo('PL')],
        'precio_por_clase': ConfiguracionPrecio.get('PACK_REDUCIDO_CLASE', 20_000),
        'cantidades': range(2, 10),
        'hoy': date.today(),
    }

    if request.method == 'POST':
        frecuencia  = request.POST.get('frecuencia')
        hora_str    = request.POST.get('hora')
        fecha_str   = request.POST.get('fecha_inicio')
        cantidad_str = request.POST.get('cantidad')

        errores = []
        if frecuencia not in DIAS_SEMANA_PILATES:
            errores.append('Frecuencia no válida.')

        hora = int(hora_str) if hora_str and hora_str.isdigit() else None
        if not hora or hora not in horas_disponibles_por_tipo('PL'):
            errores.append('Hora no válida.')

        cantidad = int(cantidad_str) if cantidad_str and cantidad_str.isdigit() else None
        if not cantidad or not (2 <= cantidad <= 9):
            errores.append('La cantidad debe ser entre 2 y 9 clases.')

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < date.today():
                    errores.append('La fecha no puede ser en el pasado.')
            except ValueError:
                errores.append('Fecha no válida.')

        if not errores and frecuencia and hora and fecha_inicio:
            dias = DIAS_SEMANA_PILATES[frecuencia]
            if fecha_inicio.weekday() not in dias:
                nombres = {
                    'LMV': 'lunes, miércoles o viernes',
                    'LM':  'lunes o miércoles',
                    'MJ':  'martes o jueves',
                }
                errores.append(f'Para {frecuencia}, la primera clase debe ser un {nombres[frecuencia]}.')

        if not errores:
            fechas, sin_cupo = _slots_disponibles(frecuencia, hora, fecha_inicio, cantidad)
            if sin_cupo:
                errores.append(
                    f'Sin cupo en: {", ".join(fmt_fecha(f) for f in sin_cupo[:3])}'
                    + ('…' if len(sin_cupo) > 3 else '')
                )

        if errores:
            context.update({'errores': errores,
                            'sel_frecuencia': frecuencia,
                            'sel_hora': hora_str,
                            'sel_fecha': fecha_str,
                            'sel_cantidad': cantidad_str})
            return render(request, 'reservas/reservar_pack_reducido.html', context)

        request.session['pack_reducido_borrador'] = {
            'frecuencia':   frecuencia,
            'hora':         hora,
            'fecha_inicio': fecha_inicio.isoformat(),
            'cantidad':     cantidad,
            'fechas':       [f.isoformat() for f in fechas],
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

    fechas   = [date.fromisoformat(f) for f in borrador['fechas']]
    cantidad = borrador['cantidad']
    precio   = cantidad * ConfiguracionPrecio.get('PACK_REDUCIDO_CLASE', 20_000)

    context = {
        'frecuencia_label': {
            'LMV': 'Lun · Miérc · Vier',
            'LM':  'Lun · Miérc',
            'MJ':  'Mar · Jue',
        }[borrador['frecuencia']],
        'hora':             borrador['hora'],
        'fecha_inicio':     date.fromisoformat(borrador['fecha_inicio']),
        'fecha_fin':        fechas[-1],
        'fechas':           [(i + 1, f, fmt_fecha(f)) for i, f in enumerate(fechas)],
        'cantidad':         cantidad,
        'precio_total':     precio,
        'precio_por_clase': ConfiguracionPrecio.get('PACK_REDUCIDO_CLASE', 20_000),
    }

    if request.method == 'POST':
        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'REDUCIDO',
            frecuencia   = borrador['frecuencia'],
            hora         = borrador['hora'],
            fecha_inicio = date.fromisoformat(borrador['fecha_inicio']),
            cantidad     = cantidad,
        )
        del request.session['pack_reducido_borrador']
        crear_sesiones_pack(pack)
        messages.success(request, f'¡Reserva confirmada! Tu primera clase es el {fmt_fecha(fechas[0])} a las {borrador["hora"]:02d}:00.')
        return redirect('mis_clases')

    return render(request, 'reservas/reservar_pack_reducido_confirmar.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_suelta(request):
    context = {
        'horas': [{'valor': h, 'label': f'{h:02d}:00'} for h in horas_disponibles_por_tipo('PL')],
        'precio': ConfiguracionPrecio.get('CLASE_SUELTA', 25_000),
        'hoy': date.today(),
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
                if fecha_inicio.weekday() > 4:
                    errores.append('Las clases sueltas son solo de lunes a viernes.')
            except ValueError:
                errores.append('Fecha no válida.')

        if not errores and hora and fecha_inicio:
            if Sesion.cupos_disponibles(fecha_inicio, hora) < 1:
                errores.append(f'Sin cupo disponible el {fmt_fecha(fecha_inicio)} a las {hora:02d}:00.')

        if errores:
            context.update({'errores': errores,
                            'sel_hora': hora_str,
                            'sel_fecha': fecha_str})
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
        messages.warning(request, 'Sesión expirada. Inicia la reserva de nuevo.')
        return redirect('reservar_clase_suelta')

    fecha = date.fromisoformat(borrador['fecha_inicio'])
    hora  = borrador['hora']

    context = {
        'fecha':       fecha,
        'fecha_label': fmt_fecha(fecha),
        'hora':        hora,
        'precio': ConfiguracionPrecio.get('CLASE_SUELTA', 25_000),
    }

    if request.method == 'POST':
        # Verificar cupo de nuevo antes de crear
        if Sesion.cupos_disponibles(fecha, hora) < 1:
            messages.error(request, 'Lo sentimos, el cupo se ocupó mientras confirmabas. Elige otro horario.')
            return redirect('reservar_clase_suelta')

        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'SUELTA',
            hora         = hora,
            fecha_inicio = fecha,
            cantidad     = 1,
        )
        Sesion.objects.create(
            pack   = pack,
            fecha  = fecha,
            hora   = hora,
            numero = 1,
        )
        pack.fecha_fin = fecha
        pack.estado    = 'ACTIVO'
        pack.save(update_fields=['fecha_fin', 'estado'])

        del request.session['clase_suelta_borrador']
        messages.success(request, f'¡Clase reservada! Te esperamos el {fmt_fecha(fecha)} a las {hora:02d}:00.')
        return redirect('mis_clases')

    return render(request, 'reservas/reservar_clase_suelta_confirmar.html', context)



@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_prueba(request):
    hoy = date.today()

    context = {
        'precio': ConfiguracionPrecio.get('CLASE_PRUEBA', 15_000),
        'hora':     '12:30',
        'duracion': '45 minutos',
        'hoy':      hoy,
    }

    if request.method == 'POST':
        fecha_str = request.POST.get('fecha_inicio')
        errores = []

        fecha_inicio = None
        if fecha_str:
            try:
                fecha_inicio = date.fromisoformat(fecha_str)
                if fecha_inicio < hoy:
                    errores.append('La fecha no puede ser en el pasado.')
                if fecha_inicio.weekday() != 5:
                    errores.append('La clase de prueba es solo los sábados.')
                if fecha_inicio and Sesion.cupos_disponibles(fecha_inicio, 12) < 1:
                    errores.append('No hay cupo disponible ese sábado.')
            except ValueError:
                errores.append('Fecha no válida.')
        else:
            errores.append('Debes elegir un sábado.')

        if errores:
            context['errores'] = errores
            context['sel_fecha'] = fecha_str
            return render(request, 'reservas/reservar_clase_prueba.html', context)

        request.session['clase_prueba_borrador'] = {
            'fecha_inicio': fecha_inicio.isoformat(),
        }
        return redirect('reservar_clase_prueba_confirmar')

    return render(request, 'reservas/reservar_clase_prueba.html', context)



# ─── RESERVAR CLASE DE PRUEBA ──────────────────────

@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_prueba_confirmar(request):
    borrador = request.session.get('clase_prueba_borrador')
    if not borrador:
        messages.warning(request, 'Sesión expirada. Inicia la reserva de nuevo.')
        return redirect('reservar_clase_prueba')

    fecha = date.fromisoformat(borrador['fecha_inicio'])

    context = {
        'fecha':       fecha,
        'fecha_label': fmt_fecha(fecha),
        'hora':        '12:30',
        'duracion':    '45 minutos',
        'precio': ConfiguracionPrecio.get('CLASE_PRUEBA', 15_000),
    }

    if request.method == 'POST':
        if Sesion.cupos_disponibles(fecha, 12) < 1:
            messages.error(request, 'Lo sentimos, el cupo se ocupó. Elige otro sábado.')
            return redirect('reservar_clase_prueba')

        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'PRUEBA',
            hora         = 12,
            fecha_inicio = fecha,
            cantidad     = 1,
        )
        Sesion.objects.create(
            pack   = pack,
            fecha  = fecha,
            hora   = 12,
            numero = 1,
        )
        pack.fecha_fin = fecha
        pack.estado    = 'ACTIVO'
        pack.save(update_fields=['fecha_fin', 'estado'])

        del request.session['clase_prueba_borrador']
        messages.success(request, f'¡Clase de prueba reservada! Te esperamos el {fmt_fecha(fecha)} a las 12:30.')
        return redirect('mis_clases')

    return render(request, 'reservas/reservar_clase_prueba_confirmar.html', context)



# ─── RESERVAR CLASE PRIVADA ──────────────────────

HORAS_PRIVADAS = [11, 16]

def slot_privado_disponible(fecha: date, hora: int) -> bool:
    """
    Un slot privado está disponible solo si no hay NINGUNA sesión
    (grupal ni privada) en esa fecha y hora.
    """
    return not Sesion.objects.filter(
        fecha=fecha,
        hora=hora,
        estado__in=['PROGRAMADA', 'RECUPERAR', 'RECUPERADA'],
    ).exists()


@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_privada(request):
    context = {
        'hoy':        date.today(),
        'horas':      [{'valor': h, 'label': f'{h:02d}:00'} for h in HORAS_PRIVADAS],
        'frecuencias': [
            {'codigo': 'LMV', 'label': 'Lun · Miérc · Vier', 'dias': '3 días/semana'},
            {'codigo': 'LM',  'label': 'Lun · Miérc',         'dias': '2 días/semana'},
            {'codigo': 'MJ',  'label': 'Mar · Jue',            'dias': '2 días/semana'},
        ],
        'precio_pack10':  ConfiguracionPrecio.get('PRIVADA_PACK10', 285_000),
        'precio_reducido': ConfiguracionPrecio.get('PRIVADA_CLASE', 30_000),
    }

    if request.method == 'POST':
        tipo        = request.POST.get('tipo')       # PRIVADA10 o PRIVADA_REDUCIDO
        frecuencia  = request.POST.get('frecuencia')
        hora_str    = request.POST.get('hora')
        fecha_str   = request.POST.get('fecha_inicio')
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
                    nombres = {
                        'LMV': 'lunes, miércoles o viernes',
                        'LM':  'lunes o miércoles',
                        'MJ':  'martes o jueves',
                    }
                    errores.append(f'La fecha debe ser un {nombres.get(frecuencia, "")}.')
            except ValueError:
                errores.append('Fecha no válida.')
        else:
            errores.append('Debes elegir una fecha de inicio.')

        if not errores and fecha_inicio and hora and frecuencia:
            fechas = generar_fechas_pack(fecha_inicio, frecuencia, cantidad)
            sin_cupo = [f for f in fechas if not slot_privado_disponible(f, hora)]
            if sin_cupo:
                errores.append(
                    f'Paula no está disponible en: '
                    + ', '.join(fmt_fecha(f) for f in sin_cupo[:3])
                    + ('…' if len(sin_cupo) > 3 else '')
                )

        if errores:
            context.update({
                'errores':       errores,
                'sel_tipo':      tipo,
                'sel_frecuencia': frecuencia,
                'sel_hora':      hora_str,
                'sel_fecha':     fecha_str,
                'sel_cantidad':  cantidad_str,
            })
            return render(request, 'reservas/reservar_clase_privada.html', context)

        precio = ConfiguracionPrecio.get('PRIVADA_PACK10', 285_000) if tipo == 'PRIVADA10' else cantidad * ConfiguracionPrecio.get('PRIVADA_CLASE', 30_000)

        request.session['privada_borrador'] = {
            'tipo':         tipo,
            'frecuencia':   frecuencia,
            'hora':         hora,
            'fecha_inicio': fecha_inicio.isoformat(),
            'cantidad':     cantidad,
            'fechas':       [f.isoformat() for f in fechas],
            'precio':       precio,
        }
        return redirect('reservar_clase_privada_confirmar')

    return render(request, 'reservas/reservar_clase_privada.html', context)


@login_required
@require_http_methods(["GET", "POST"])
def reservar_clase_privada_confirmar(request):
    borrador = request.session.get('privada_borrador')
    if not borrador:
        messages.warning(request, 'Sesión expirada. Inicia la reserva de nuevo.')
        return redirect('reservar_clase_privada')

    fechas   = [date.fromisoformat(f) for f in borrador['fechas']]
    cantidad = borrador['cantidad']
    tipo     = borrador['tipo']

    context = {
        'tipo_label': 'Pack 10 Clases Privadas' if tipo == 'PRIVADA10' else f'Pack {cantidad} Clases Privadas',
        'frecuencia_label': {
            'LMV': 'Lun · Miérc · Vier',
            'LM':  'Lun · Miérc',
            'MJ':  'Mar · Jue',
        }[borrador['frecuencia']],
        'hora':         borrador['hora'],
        'fecha_inicio': fechas[0],
        'fecha_fin':    fechas[-1],
        'fechas':       [(i + 1, f, fmt_fecha(f)) for i, f in enumerate(fechas)],
        'cantidad':     cantidad,
        'precio':       borrador['precio'],
        'precio_por_clase': ConfiguracionPrecio.get('PRIVADA_PACK10', 285_000) // 10 if tipo == 'PRIVADA10' else ConfiguracionPrecio.get('PRIVADA_CLASE', 30_000),
    }

    if request.method == 'POST':
        # Verificar disponibilidad de nuevo
        hora = borrador['hora']
        sin_cupo = [f for f in fechas if not slot_privado_disponible(f, hora)]
        if sin_cupo:
            messages.error(request, 'Un horario se ocupó mientras confirmabas. Intenta de nuevo.')
            return redirect('reservar_clase_privada')

        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'PRIVADA',
            frecuencia   = borrador['frecuencia'],
            hora         = hora,
            fecha_inicio = fechas[0],
            cantidad     = cantidad,
        )
        crear_sesiones_pack(pack)

        del request.session['privada_borrador']
        messages.success(request, f'¡Clase privada reservada! Tu primera clase es el {fmt_fecha(fechas[0])} a las {hora:02d}:00.')
        return redirect('mis_clases')

    return render(request, 'reservas/reservar_clase_privada_confirmar.html', context)