from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from .services import SMSService


@login_required
def test_sms(request):
    """
    Test SMS sending (for development only).
    """
    if request.method == 'POST':
        phone = request.POST.get('phone')
        message = request.POST.get('message')
        
        sms_service = SMSService()
        result = sms_service.send_sms(phone, message)
        
        return JsonResponse(result)
    
    return render(request, 'notifications/test.html')
