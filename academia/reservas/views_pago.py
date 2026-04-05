# views_pago.py
import mercadopago
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Pack, crear_sesiones_pack

sdk = mercadopago.SDK(settings.MERCADOPAGO_ACCESS_TOKEN)


def crear_preferencia_mp(pack: Pack, request) -> str:
    """
    Crea una preferencia en MercadoPago y retorna el preference_id.
    """
    base_url = request.build_absolute_uri('/')[:-1]  # ej: http://localhost:8000

    preference_data = {
        "items": [
            {
                "id":          f"{pack.tipo}-{pack.pk}",
                "title":       pack.get_tipo_display(),
                "quantity":    1,
                "currency_id": "CLP",
                "unit_price":  pack.precio_total,
            }
        ],
        "payer": {
            "name":  request.user.first_name,
            "surname": request.user.last_name,
            "email": request.user.email,
        },
        "back_urls": {
            "success": f"{base_url}/pago/exitoso/",
            "failure": f"{base_url}/pago/fallido/",
            "pending": f"{base_url}/pago/pendiente/",
        },
        "auto_return":        "approved",
        "external_reference": f"{pack.tipo}-{pack.pk}-{request.user.pk}",
        "statement_descriptor": "PAULA PILATES",
    }

    result = sdk.preference().create(preference_data)
    preference = result["response"]
    return preference["id"]


@login_required
def pago_exitoso(request):
    """MP redirige aquí tras pago aprobado."""
    payment_id      = request.GET.get('payment_id')
    status          = request.GET.get('status')
    external_ref    = request.GET.get('external_reference')

    if status != 'approved' or not payment_id:
        messages.error(request, 'El pago no fue aprobado.')
        return redirect('mis_clases')

    # Verificar con la API de MP que el pago es real
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

    # Evitar doble activación
    if pack.estado != 'PENDIENTE_PAGO':
        messages.info(request, 'Tu reserva ya estaba activada.')
        return redirect('mis_clases')

    # Activar el pack según su tipo
    if pack.tipo in ('PACK10', 'REDUCIDO', 'PRIVADA'):
        crear_sesiones_pack(pack)          # crea sesiones + pone ACTIVO
    else:
        # Clase suelta, prueba, BB — la sesión ya fue creada al confirmar
        pack.estado = 'ACTIVO'
        pack.save(update_fields=['estado'])

    messages.success(request, f'¡Pago confirmado! Tu {pack.get_tipo_display()} está activo.')
    return redirect('mis_clases')


@login_required
def pago_fallido(request):
    messages.error(request, 'El pago falló o fue rechazado. Puedes intentarlo de nuevo.')
    return redirect('mis_clases')


@login_required
def pago_pendiente(request):
    messages.warning(request, 'Tu pago está pendiente. Te avisaremos cuando se confirme.')
    return redirect('mis_clases')
