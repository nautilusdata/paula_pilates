from django.shortcuts import redirect
from django.contrib.auth.decorators import login_required

def home(request):
    if request.user.is_authenticated:
        return redirect('panel_principal' if request.user.is_staff else 'mis_clases')
    return redirect('account_login')

@login_required
def login_redirect(request):
    if request.user.is_staff:
        return redirect('panel_principal')
    return redirect('mis_clases')