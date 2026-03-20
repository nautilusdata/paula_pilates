from django.urls import path
from . import views_reservar_pack10
from . import views_mis_clases


urlpatterns = [
    path('reservar/pack10/', views_reservar_pack10.reservar_pack10, name='reservar_pack10'),
    path('reservar/pack10/confirmar/', views_reservar_pack10.reservar_pack10_confirmar, name='reservar_pack10_confirmar'),
    path('reservar/pack10/horas/', views_reservar_pack10.horas_disponibles_ajax, name='horas_disponibles_ajax'),
    path('mis-clases/', views_mis_clases.mis_clases, name='mis_clases'),
    path('reservar/pack-reducido/', views_reservar_pack10.reservar_pack_reducido, name='reservar_pack_reducido'),
    path('reservar_pack_reducido/confirmar/', views_reservar_pack10.reservar_pack_reducido_confirmar, name='reservar_pack_reducido_confirmar'),
    path('reservar/clase-suelta/', views_reservar_pack10.reservar_clase_suelta, name='reservar_clase_suelta'),
    path('reservar/clase-suelta/confirmar/', views_reservar_pack10.reservar_clase_suelta_confirmar, name='reservar_clase_suelta_confirmar'),
]