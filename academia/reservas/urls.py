from django.urls import path
from . import views_reservar_pack10
from . import views_mis_clases
from . import views_body_balance
from . import views_panel_paula
from . import views_pago

urlpatterns = [
    path('reservar/pack10/', views_reservar_pack10.reservar_pack10, name='reservar_pack10'),
    path('reservar/pack10/confirmar/', views_reservar_pack10.reservar_pack10_confirmar, name='reservar_pack10_confirmar'),
    path('reservar/pack10/horas/', views_reservar_pack10.horas_disponibles_ajax, name='horas_disponibles_ajax'),
    path('mis-clases/', views_mis_clases.mis_clases, name='mis_clases'),
    path('reservar/pack-reducido/', views_reservar_pack10.reservar_pack_reducido, name='reservar_pack_reducido'),
    path('reservar_pack_reducido/confirmar/', views_reservar_pack10.reservar_pack_reducido_confirmar, name='reservar_pack_reducido_confirmar'),
    path('reservar/clase-suelta/', views_reservar_pack10.reservar_clase_suelta, name='reservar_clase_suelta'),
    path('reservar/clase-suelta/confirmar/', views_reservar_pack10.reservar_clase_suelta_confirmar, name='reservar_clase_suelta_confirmar'),
    path('reservar/clase-prueba/', views_reservar_pack10.reservar_clase_prueba, name='reservar_clase_prueba'),
    path('reservar/clase-prueba/confirmar/', views_reservar_pack10.reservar_clase_prueba_confirmar, name='reservar_clase_prueba_confirmar'),
    path('reservar/body-balance/', views_body_balance.reservar_body_balance, name='reservar_body_balance'),
    path('reservar/body-balance/confirmar/', views_body_balance.reservar_body_balance_confirmar, name='reservar_body_balance_confirmar'),
    path('reservar/clase-privada/', views_reservar_pack10.reservar_clase_privada, name='reservar_clase_privada'),
    path('reservar/clase-privada/confirmar/', views_reservar_pack10.reservar_clase_privada_confirmar, name='reservar_clase_privada_confirmar'),
    path('panel/', views_panel_paula.panel_principal, name='panel_principal'),
    path('panel/precios/', views_panel_paula.panel_precios, name='panel_precios'),
    path('panel/horarios/', views_panel_paula.panel_horarios, name='panel_horarios'),
    path('panel/ausente/<int:sesion_id>/', views_panel_paula.marcar_ausente, name='marcar_ausente'),
    path('recuperar/<int:sesion_id>/', views_mis_clases.recuperar_clase, name='recuperar_clase'),
    path('panel/bulk-reschedule/', views_panel_paula.bulk_reschedule, name='bulk_reschedule'),
    path('panel/bulk-reschedule/preview/', views_panel_paula.bulk_reschedule_preview, name='bulk_reschedule_preview'),
    # Pago MercadoPago
    path('pago/exitoso/',   views_pago.pago_exitoso,   name='pago_exitoso'),
    path('pago/fallido/',   views_pago.pago_fallido,   name='pago_fallido'),
    path('pago/pendiente/', views_pago.pago_pendiente, name='pago_pendiente'),
    path('pago/brick/<int:pack_id>/', views_pago.pago_brick, name='pago_brick'),
]