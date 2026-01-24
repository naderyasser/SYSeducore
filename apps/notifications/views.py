from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .services import WhatsAppService


@login_required
def test_whatsapp(request):
    """
    Test WhatsApp sending (for development only).
    """
    if request.method == 'POST':
        phone = request.POST.get('phone')
        message = request.POST.get('message')

        whatsapp_service = WhatsAppService()
        result = whatsapp_service.send_message(phone, message)

        return JsonResponse(result)

    return render(request, 'notifications/test.html')
