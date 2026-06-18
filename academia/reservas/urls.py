from django.urls import path
from . import views_reservar_pack10
from . import views_mis_clases
from . import views_body_balance
from . import views_panel_paula
from . import views_webpay

urlpatterns = [
    path('reservar/pack/<str:tier>/', views_reservar_pack10.reservar_pack, name='reservar_pack'),
    path('reservar/pack/<str:tier>/confirmar/', views_reservar_pack10.reservar_pack_confirmar, name='reservar_pack_confirmar'),
    path('reservar/pack10/horas/', views_reservar_pack10.horas_disponibles_ajax, name='horas_disponibles_ajax'),
    path('reservar/pack10/dias/', views_reservar_pack10.dias_disponibles_ajax, name='dias_disponibles_ajax'),
    path('reservar/pack4/', views_reservar_pack10.reservar_pack4, name='reservar_pack4'),
    path('reservar/pack4/confirmar/', views_reservar_pack10.reservar_pack4_confirmar, name='reservar_pack4_confirmar'),
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
    path('panel/alumna/<int:alumna_id>/', views_panel_paula.ficha_alumna, name='ficha_alumna'),
    path('panel/cancelar-pack/<int:pack_id>/', views_panel_paula.cancelar_pack, name='cancelar_pack'),
    path('panel/reprogramar/<int:sesion_id>/', views_panel_paula.reprogramar_sesion, name='reprogramar_sesion'),
    path('panel/reprogramar/<int:sesion_id>/confirmar/', views_panel_paula.reprogramar_sesion_confirmar, name='reprogramar_sesion_confirmar'),
    path('panel/reprogramar/<int:sesion_id>/horas/', views_panel_paula.reprogramar_horas_ajax, name='reprogramar_horas_ajax'),
    path('panel/completada/<int:sesion_id>/', views_panel_paula.marcar_completada, name='marcar_completada'),
    path('panel/alumnas/', views_panel_paula.panel_alumnas, name='panel_alumnas'),
    path('panel/bulk-reschedule/', views_panel_paula.bulk_reschedule, name='bulk_reschedule'),
    path('panel/bulk-reschedule/preview/', views_panel_paula.bulk_reschedule_preview, name='bulk_reschedule_preview'),
    path('pago/webpay/iniciar/<int:pack_id>/', views_webpay.webpay_iniciar, name='webpay_iniciar'),
    path('pago/webpay/retorno/', views_webpay.webpay_retorno, name='webpay_retorno'),
    path('pago/reintentar/<int:pack_id>/', views_webpay.reintentar_pago, name='reintentar_pago'),
    path('internal/limpiar-packs/', views_panel_paula.limpiar_packs_view, name='limpiar_packs'),
]
