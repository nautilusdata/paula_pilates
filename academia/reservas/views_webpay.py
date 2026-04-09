# views_webpay.py
import random
import string
import logging

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
from transbank.error.transbank_error import TransbankError

logger = logging.getLogger(__name__)


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
    # Evitar compras en $0 si hay desconexión con la DB y el precio queda en fallback.
    if pack.precio_total == 0:
        raise ValueError('Precio inválido. Verifica la configuración de precios.')

    response = _tx().create(
        buy_order  = f"PACK-{pack.pk}",
        session_id = _session_id(),
        amount     = float(pack.precio_total),
        return_url = return_url,
    )
    logger.info("WEBPAY CREAR pack=%s response=%s", pack.pk, response)
    return response  # dict con 'token' y 'url'


def verificar_transaccion(token: str) -> dict:
    response = _tx().commit(token)
    logger.info("WEBPAY COMMIT token=%s response=%s", token[:8], response)
    return response


def _activar_pack(pack: Pack):
    """Crea las sesiones y activa el pack según su tipo. Idempotente: no hace nada si ya está ACTIVO."""
    if pack.estado == 'ACTIVO':
        return

    if pack.tipo in ('PACK10', 'REDUCIDO', 'PRIVADA'):
        crear_sesiones_pack(pack)  # pone estado ACTIVO internamente

    elif pack.tipo in ('SUELTA', 'PRUEBA'):
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


# ── Iniciar pago ─────────────────────────────────────────────────────────────

@login_required
@require_POST
def webpay_iniciar(request, pack_id):
    pack = get_object_or_404(Pack, pk=pack_id, alumna=request.user, estado='PENDIENTE_PAGO')
    return_url = request.build_absolute_uri('/pago/webpay/retorno/')

    try:
        data = crear_transaccion(pack, return_url)
    except (TransbankError, ValueError, Exception) as e:
        logger.error("Error creando transacción Webpay pack=%s: %s", pack_id, e)
        messages.error(request, 'Error al conectar con Webpay. Intenta de nuevo.')
        return redirect('mis_clases')

    token = data.get('token')
    url   = data.get('url')

    if not token or not url:
        messages.error(request, 'Respuesta inesperada de Webpay. Intenta de nuevo.')
        return redirect('mis_clases')

    request.session[f'webpay_token_{pack_id}'] = token
    request.session['webpay_pack_id'] = pack_id

    return render(request, 'reservas/webpay_redirect.html', {'url': url, 'token': token})


# ── Retorno de Webpay ─────────────────────────────────────────────────────────

def webpay_retorno(request):
    """
    Webpay puede volver por tres caminos distintos:

    1. Pago completado (aprobado o rechazado):
       POST con token_ws

    2. Alumna presionó "Volver al comercio" / abandonó:
       GET con TBK_TOKEN  (sin token_ws)

    3. Timeout de sesión Webpay (>10 min sin pagar):
       POST con TBK_TOKEN y TBK_ORDER_ID (sin token_ws)
    """

    tbk_token = request.POST.get('TBK_TOKEN') or request.GET.get('TBK_TOKEN')
    token_ws  = request.POST.get('token_ws')  or request.GET.get('token_ws')

    # ── Caso 2 y 3: abandono o timeout ───────────────────────────────────────
    if tbk_token and not token_ws:
        logger.warning("WEBPAY abandono/timeout TBK_TOKEN=%s", tbk_token[:8])
        messages.warning(request, 'Cancelaste el pago o la sesión expiró. Puedes intentarlo cuando quieras.')
        return redirect('mis_clases')

    # ── Sin token: situación inesperada ───────────────────────────────────────
    if not token_ws:
        logger.error("WEBPAY retorno sin token_ws ni TBK_TOKEN")
        messages.error(request, 'No se recibió confirmación de Webpay.')
        return redirect('mis_clases')

    # ── Caso 1: confirmar con Transbank ──────────────────────────────────────
    try:
        data = verificar_transaccion(token_ws)
    except TransbankError as e:
        logger.error("WEBPAY commit error token=%s: %s", token_ws[:8], e)
        messages.error(request, 'Error al confirmar el pago con Webpay. Contacta a Paula.')
        return redirect('mis_clases')

    response_code = data.get('response_code')
    status        = data.get('status')
    buy_order     = data.get('buy_order', '')

    logger.info("WEBPAY retorno buy_order=%s status=%s response_code=%s", buy_order, status, response_code)

    # Extraer pack_id del buy_order (formato "PACK-48")
    try:
        pack_id = int(buy_order.replace('PACK-', ''))
    except (ValueError, AttributeError):
        logger.error("WEBPAY buy_order inválido: %s", buy_order)
        messages.error(request, 'Error al identificar tu reserva.')
        return redirect('mis_clases')

    pack = get_object_or_404(Pack, pk=pack_id)

    # Idempotencia: si ya estaba activado (doble POST), no hacer nada
    if pack.estado != 'PENDIENTE_PAGO':
        messages.info(request, 'Tu reserva ya estaba activada.')
        return redirect('mis_clases')

    # ── Pago aprobado ─────────────────────────────────────────────────────────
    if response_code == 0 and status == 'AUTHORIZED':
        try:
            _activar_pack(pack)
        except Exception as e:
            logger.error("Error activando pack=%s tras pago aprobado: %s", pack_id, e)
            messages.error(request, 'Pago recibido, pero hubo un error activando tu reserva. Avisa a Paula con urgencia.')
            return redirect('mis_clases')

        messages.success(request, f'¡Pago confirmado! Tu {pack.get_tipo_display()} está activo. 🎉')
        return redirect('mis_clases')

    # ── Pago rechazado ────────────────────────────────────────────────────────
    logger.warning("WEBPAY pago rechazado pack=%s response_code=%s status=%s", pack_id, response_code, status)
    messages.error(request, 'El pago fue rechazado. Verifica los datos de tu tarjeta e intenta de nuevo.')
    return redirect('mis_clases')


# ── Reintentar pago desde "Mis Clases" ───────────────────────────────────────

@login_required
def reintentar_pago(request, pack_id):
    pack = get_object_or_404(Pack, pk=pack_id, alumna=request.user, estado='PENDIENTE_PAGO')
    return_url = request.build_absolute_uri('/pago/webpay/retorno/')

    try:
        data = crear_transaccion(pack, return_url)
    except (TransbankError, ValueError, Exception) as e:
        logger.error("Error reintentando pago Webpay pack=%s: %s", pack_id, e)
        messages.error(request, 'Error al conectar con Webpay. Intenta de nuevo.')
        return redirect('mis_clases')

    token = data.get('token')
    url   = data.get('url')

    if not token or not url:
        messages.error(request, 'Respuesta inesperada de Webpay. Intenta de nuevo.')
        return redirect('mis_clases')

    request.session['webpay_pack_id'] = pack.pk

    return render(request, 'reservas/webpay_redirect.html', {'url': url, 'token': token})