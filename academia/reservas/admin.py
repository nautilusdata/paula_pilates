from django.contrib import admin
from .models import UserMetadata, Pack, Sesion
from .models import UserMetadata, Pack, Sesion, ConfiguracionHorario

admin.site.register(UserMetadata)
admin.site.register(Pack)
admin.site.register(Sesion)
admin.site.register(ConfiguracionHorario)