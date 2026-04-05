# views_pago.py  — reemplaza el archivo completo
from django.http import JsonResponse
import mercadopago
from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Pack, Sesion, crear_sesiones_pack, generar_fechas_pack
import json
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)


def crear_preferencia_mp(pack: Pack, request) -> str:
    base_url = request.build_absolute_uri('/')[:-1]
    preference_data = {
        "items": [{
            "id":          f"{pack.tipo}-{pack.pk}",
            "title":       pack.get_tipo_display(),
            "quantity":    1,
            "currency_id": "CLP",
            "unit_price":  pack.precio_total,
        }],
        "payer": {
            "name":    request.user.first_name,
            "surname": request.user.last_name,
            "email":   request.user.email,
        },
        "back_urls": {
            "success": f"{base_url}/pago/exitoso/",
            "failure": f"{base_url}/pago/fallido/",
            "pending": f"{base_url}/pago/pendiente/",
        },
        #"auto_return":          "approved",
        "external_reference":   f"{pack.tipo}-{pack.pk}-{request.user.pk}",
        "statement_descriptor": "PAULA PILATES",
    }
    result     = sdk.preference().create(preference_data)
    preference = result["response"]
    print(">>> MP RESPONSE:", preference)  # ← debug temporal
    return preference["id"]


@login_required
def pago_brick(request, pack_id):
    """Renderiza la página con el Brick de MercadoPago."""
    pack = get_object_or_404(Pack, pk=pack_id, alumna=request.user, estado='PENDIENTE_PAGO')
    preference_id = request.session.get(f'mp_pref_{pack_id}')
    if not preference_id:
        messages.error(request, 'Sesión de pago expirada. Inicia la reserva de nuevo.')
        return redirect('mis_clases')

    return render(request, 'reservas/pago_brick.html', {
        'pack':           pack,
        'preference_id':  preference_id,
        'public_key':     settings.MERCADOPAGO_PUBLIC_KEY,
    })


@login_required
def pago_exitoso(request):
    """MP redirige aquí tras pago aprobado."""
    payment_id   = request.GET.get('payment_id')
    status       = request.GET.get('status')
    external_ref = request.GET.get('external_reference')

    if status != 'approved' or not payment_id:
        messages.error(request, 'El pago no fue aprobado.')
        return redirect('mis_clases')

    # Verificar con la API que el pago es real
    result = sdk.payment().get(payment_id)
    pago   = result["response"]
    if pago.get("status") != "approved":
        messages.error(request, 'No pudimos confirmar tu pago. Contacta a Paula.')
        return redirect('mis_clases')

    # Extraer pack_id del external_reference  (ej: "PACK10-42-7")
    try:
        partes  = external_ref.split('-')
        pack_id = int(partes[1])
    except (IndexError, ValueError, TypeError):
        messages.error(request, 'Error al identificar tu reserva.')
        return redirect('mis_clases')

    pack = get_object_or_404(Pack, pk=pack_id, alumna=request.user)

    if pack.estado != 'PENDIENTE_PAGO':
        messages.info(request, 'Tu reserva ya estaba activada.')
        return redirect('mis_clases')

    # Activar según tipo
    if pack.tipo in ('PACK10', 'REDUCIDO', 'PRIVADA'):
        crear_sesiones_pack(pack)  # crea sesiones + pone ACTIVO

    elif pack.tipo == 'SUELTA':
        Sesion.objects.create(pack=pack, fecha=pack.fecha_inicio, hora=pack.hora, numero=1)
        pack.fecha_fin = pack.fecha_inicio
        pack.estado    = 'ACTIVO'
        pack.save(update_fields=['fecha_fin', 'estado'])

    elif pack.tipo == 'PRUEBA':
        Sesion.objects.create(pack=pack, fecha=pack.fecha_inicio, hora=pack.hora, numero=1)
        pack.fecha_fin = pack.fecha_inicio
        pack.estado    = 'ACTIVO'
        pack.save(update_fields=['fecha_fin', 'estado'])

    elif pack.tipo == 'BB_FULL':
        from .views_body_balance import generar_fechas_bb_full
        fechas   = generar_fechas_bb_full(pack.fecha_inicio)
        sesiones = [Sesion(pack=pack, fecha=f, hora=pack.hora, numero=i + 1)
                    for i, f in enumerate(fechas)]
        Sesion.objects.bulk_create(sesiones)
        pack.estado = 'ACTIVO'
        pack.save(update_fields=['estado'])

    elif pack.tipo == 'BB_SEMANAL':
        Sesion.objects.create(pack=pack, fecha=pack.fecha_inicio, hora=pack.hora, numero=1)
        pack.estado = 'ACTIVO'
        pack.save(update_fields=['estado'])

    # Limpiar preferencia de sesión
    request.session.pop(f'mp_pref_{pack.pk}', None)

    messages.success(request, f'¡Pago confirmado! Tu {pack.get_tipo_display()} está activo. 🎉')
    return redirect('mis_clases')


@login_required
def pago_fallido(request):
    messages.error(request, 'El pago falló o fue rechazado. Puedes intentarlo de nuevo.')
    return redirect('mis_clases')


@login_required
def pago_pendiente(request):
    messages.warning(request, 'Tu pago está pendiente. Te avisaremos cuando se confirme.')
    return redirect('mis_clases')


@login_required
@require_POST
def pago_procesar(request):
    """Recibe formData del Brick, procesa el pago con MP SDK."""
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({'error': 'Datos inválidos'}, status=400)

    # Obtener el pack pendiente de este usuario
    pack = Pack.objects.filter(
        alumna=request.user,
        estado='PENDIENTE_PAGO'
    ).order_by('-creado_en').first()

    if not pack:
        return JsonResponse({'error': 'No hay reserva pendiente'}, status=404)

    # Agregar external_reference al pago
    data['external_reference'] = f"{pack.tipo}-{pack.pk}-{request.user.pk}"

    result = sdk.payment().create(data)
    pago   = result['response']
    status = pago.get('status')

    if status == 'approved':
        redirect_url = (
            f"/pago/exitoso/"
            f"?payment_id={pago['id']}"
            f"&status=approved"
            f"&external_reference={data['external_reference']}"
        )
        return JsonResponse({'status': 'approved', 'redirect_url': redirect_url})

    elif status == 'in_process':
        return JsonResponse({'status': 'pending'})

    else:
        return JsonResponse({'status': 'rejected'})