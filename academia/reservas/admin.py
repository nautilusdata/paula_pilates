from django.contrib import admin
from .models import UserMetadata, Pack, Sesion
from .models import UserMetadata, Pack, Sesion, ConfiguracionHorario, ConfiguracionGeneral, ConfiguracionPrecio


admin.site.register(UserMetadata)
admin.site.register(Pack)
admin.site.register(Sesion)
admin.site.register(ConfiguracionHorario)
admin.site.register(ConfiguracionGeneral)
admin.site.register(ConfiguracionPrecio)