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
    Pack, Sesion, HORAS_PILATES, DIAS_SEMANA_PILATES,
    generar_fechas_pack, crear_sesiones_pack, feriados_punta_arenas
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
            for h in HORAS_PILATES
        ],
        'precio_total': 140_000,
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
        if hora and hora not in HORAS_PILATES:
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
    POST: Crea el Pack (estado PENDIENTE_PAGO) y redirige a WebPay.
    """
    borrador = request.session.get('pack10_borrador')
    if not borrador:
        messages.warning(request, 'Sesión expirada. Inicia la reserva de nuevo.')
        return redirect('reservar_pack10')

    fechas = [date.fromisoformat(f) for f in borrador['fechas']]
    feriados = feriados_punta_arenas()
    feriados_en_pack = [f for f in fechas if f in feriados]   # debería ser vacío, pero por si acaso

    context = {
        'frecuencia_label': {
            'LMV': 'Lun · Miérc · Vier',
            'LM':  'Lun · Miérc',
            'MJ':  'Mar · Jue',
        }[borrador['frecuencia']],
        'hora':         borrador['hora'],
        'fecha_inicio': date.fromisoformat(borrador['fecha_inicio']),
        'fecha_fin':    fechas[-1],
        'fechas':       [(i + 1, f, fmt_fecha(f)) for i, f in enumerate(fechas)],
        'precio_total': 140_000,
        'precio_por_clase': 14_000,
    }

    if request.method == 'POST':
        # Crear Pack en estado PENDIENTE_PAGO
        pack = Pack.objects.create(
            alumna       = request.user,
            tipo         = 'PACK10',
            frecuencia   = borrador['frecuencia'],
            hora         = borrador['hora'],
            fecha_inicio = date.fromisoformat(borrador['fecha_inicio']),
            cantidad     = 10,
        )
        # Limpiar borrador de sesión
        del request.session['pack10_borrador']

        # TODO: Integrar Transbank / Flow aquí.
        # Por ahora simulamos pago exitoso directo (para desarrollo):
        crear_sesiones_pack(pack)
        messages.success(request, f'¡Reserva confirmada! Tu primer clase es el {fmt_fecha(fechas[0])} a las {borrador["hora"]:02d}:00.')
        return redirect('mis_clases')

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

    if frecuencia not in DIAS_SEMANA_PILATES or not fecha_str:
        return JsonResponse({'error': 'Parámetros inválidos'}, status=400)

    try:
        fecha_inicio = date.fromisoformat(fecha_str)
    except ValueError:
        return JsonResponse({'error': 'Fecha inválida'}, status=400)

    result = []
    for h in HORAS_PILATES:
        fechas, sin_cupo = _slots_disponibles(frecuencia, h, fecha_inicio)
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
