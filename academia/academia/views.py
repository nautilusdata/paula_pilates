from django.http import HttpResponse

def home(request):
    if request.user.is_authenticated:
        return HttpResponse(f"¡Bienvenido, {request.user.username}! Ya estás logueado correctamente en el sistema de Pilates Paula.")
    else:
        return HttpResponse("Bienvenido. <a href='/accounts/login/'>Inicia sesión</a> o <a href='/accounts/signup/'>regístrate</a>.")
