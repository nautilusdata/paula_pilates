# views_webpay.py
from django.conf import settings
from django.shortcuts import redirect, get_object_or_404, render
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.views.decorators.http import require_POST
from .models import Pack, Sesion, crear_sesiones_pack
from transbank.webpay.webpay_plus.transaction import Transaction
from transbank.common.integration_commerce_codes import IntegrationCommerceCodes
from transbank.common.integration_api_keys import IntegrationApiKeys
from transbank.common.options import WebpayOptions
from transbank.common.integration_type import IntegrationType
import random
import string


def _session_id():
    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))


def _tx():
    options = WebpayOptions(
        IntegrationCommerceCodes.WEBPAY_PLUS,
        IntegrationApiKeys.WEBPAY,
        IntegrationType.TEST
    )
    return Transaction(options)


def crear_transaccion(pack: Pack, return_url: str) -> dict:
    # el if siguiene es debido a que los fallback son precio 0 si hay desconexión con la DB. Y para evitar compras en 0$ hacemos el if.
    if pack.preio_total == 0:
        raise ValueError('Precio inválido. Verifica la configuración de precios.')
    
    response = _tx().create(
        buy_order  = f"PACK-{pack.pk}",
        session_id = _session_id(),
        amount     = float(pack.precio_total),
        return_url = return_url,
    )
    print(">>> WEBPAY CREAR:", response)
    return response  # ya es dict con 'token' y 'url'


def verificar_transaccion(token: str) -> dict:
    response = _tx().commit(token)
    print(">>> WEBPAY VERIFICAR:", response)
    return response  # ya es dict


@login_required
@require_POST
def webpay_iniciar(request, pack_id):
    pack = get_object_or_404(Pack, pk=pack_id, alumna=request.user, estado='PENDIENTE_PAGO')
    return_url = request.build_absolute_uri('/pago/webpay/retorno/')
    data = crear_transaccion(pack, return_url)

    token = data.get('token')
    url   = data.get('url')

    if not token or not url:
        messages.error(request, 'Error al conectar con Webpay. Intenta de nuevo.')
        return redirect('mis_clases')

    request.session[f'webpay_token_{pack_id}'] = token
    request.session['webpay_pack_id'] = pack_id

    return render(request, 'reservas/webpay_redirect.html', {
        'url':   url,
        'token': token,
    })



def webpay_retorno(request):
    token = request.GET.get('token_ws') or request.POST.get('token_ws')

    if not token:
        messages.error(request, 'No se recibió confirmación de Webpay.')
        return redirect('/')

    # Verificar con Transbank primero para obtener el buy_order
    data = verificar_transaccion(token)
    print(">>> RETORNO DATA:", data)

    response_code = data.get('response_code')
    status        = data.get('status')
    buy_order     = data.get('buy_order', '')

    # Extraer pack_id del buy_order (formato "PACK-48")
    try:
        pack_id = int(buy_order.replace('PACK-', ''))
    except (ValueError, AttributeError):
        messages.error(request, 'Error al identificar tu reserva.')
        return redirect('/')

    pack = get_object_or_404(Pack, pk=pack_id)

    if pack.estado != 'PENDIENTE_PAGO':
        messages.info(request, 'Tu reserva ya estaba activada.')
        return redirect('/')

    if response_code == 0 and status == 'AUTHORIZED':
        if pack.tipo in ('PACK10', 'REDUCIDO', 'PRIVADA'):
            crear_sesiones_pack(pack)
        elif pack.tipo in ('SUELTA', 'PRUEBA'):
            Sesion.objects.create(pack=pack, fecha=pack.fecha_inicio, hora=pack.hora, numero=1)
            pack.fecha_fin = pack.fecha_inicio
            pack.estado    = 'ACTIVO'
            pack.save(update_fields=['fecha_fin', 'estado'])
        elif pack.tipo == 'BB_FULL':
            from .views_body_balance import generar_fechas_bb_full
            fechas = generar_fechas_bb_full(pack.fecha_inicio)
            sesiones = [Sesion(pack=pack, fecha=f, hora=pack.hora, numero=i+1)
                       for i, f in enumerate(fechas)]
            Sesion.objects.bulk_create(sesiones)
            pack.estado = 'ACTIVO'
            pack.save(update_fields=['estado'])
        elif pack.tipo == 'BB_SEMANAL':
            Sesion.objects.create(pack=pack, fecha=pack.fecha_inicio, hora=pack.hora, numero=1)
            pack.estado = 'ACTIVO'
            pack.save(update_fields=['estado'])

        messages.success(request, f'¡Pago confirmado! Tu {pack.get_tipo_display()} está activo. 🎉')
        return redirect('/')

    else:
        messages.error(request, 'El pago fue rechazado o cancelado. Puedes intentarlo de nuevo.')
        return redirect('/')