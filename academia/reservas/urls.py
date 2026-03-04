from django.urls import path
from . import views_reservar_pack10
from . import views_mis_clases


urlpatterns = [
    path('reservar/pack10/', views_reservar_pack10.reservar_pack10, name='reservar_pack10'),
    path('reservar/pack10/confirmar/', views_reservar_pack10.reservar_pack10_confirmar, name='reservar_pack10_confirmar'),
    path('reservar/pack10/horas/', views_reservar_pack10.horas_disponibles_ajax, name='horas_disponibles_ajax'),
    path('mis-clases/', views_mis_clases.mis_clases, name='mis_clases'),
]