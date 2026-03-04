from django.urls import path
from . import views_reservar_pack10

urlpatterns = [
    path('reservar/pack10/', views_reservar_pack10.reservar_pack10, name='reservar_pack10'),
    path('reservar/pack10/confirmar/', views_reservar_pack10.reservar_pack10_confirmar, name='reservar_pack10_confirmar'),
    path('reservar/pack10/horas/', views_reservar_pack10.horas_disponibles_ajax, name='horas_disponibles_ajax'),
]