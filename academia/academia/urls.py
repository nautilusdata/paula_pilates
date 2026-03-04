from django.contrib import admin
from django.urls import path, include
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static
from reservas import views as reservas_views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('accounts/', include('allauth.urls')),
    path('', TemplateView.as_view(template_name='home.html'), name='home'),
    path('registro/', reservas_views.registro, name='registro'),
    path('dashboard/', TemplateView.as_view(template_name='dashboard.html'), name='dashboard'),
    path('reservar/', TemplateView.as_view(template_name='reservar.html'), name='reservar'),
    path('perfil/', reservas_views.perfil, name='perfil'),
    path('reglamento/', TemplateView.as_view(template_name='reglamento.html'), name='reglamento'),
    path('', include('reservas.urls')),  # ← agregar esta línea
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)