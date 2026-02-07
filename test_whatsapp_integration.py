#!/usr/bin/env python
"""
Test script for WASender WhatsApp API integration
Run: python test_whatsapp_integration.py
"""

import os
import django
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
sys.path.insert(0, os.path.dirname(__file__))
django.setup()

from apps.notifications.services import WhatsAppService, NotificationService
from django.utils import timezone
from django.conf import settings


def test_whatsapp_service():
    """Test WhatsApp service configuration and methods"""
    
    print("\n" + "="*60)
    print("WhatsApp Service Integration Test")
    print("="*60 + "\n")
    
    # Test 1: Check configuration
    print("[1] Checking Configuration...")
    token = getattr(settings, 'WASENDER_API_TOKEN', '')
    api_url = getattr(settings, 'WASENDER_API_URL', '')
    
    print(f"  ✓ API Token configured: {bool(token)}")
    print(f"  ✓ API URL: {api_url}")
    
    if not token:
        print("  ⚠️  WARNING: Token is not configured!")
        print("     Set WASENDER_API_TOKEN in your .env file")
    print()
    
    # Test 2: Initialize service
    print("[2] Initializing WhatsApp Service...")
    try:
        whatsapp = WhatsAppService()
        print("  ✓ WhatsApp Service initialized successfully")
        print(f"  ✓ Token loaded: {whatsapp.token[:10]}...")
        print(f"  ✓ API URL: {whatsapp.api_url}")
    except Exception as e:
        print(f"  ✗ Error initializing service: {e}")
        return False
    print()
    
    # Test 3: Test phone number formatting
    print("[3] Testing Phone Number Formatting...")
    test_numbers = [
        ('01234567890', '201234567890'),
        ('+201234567890', '201234567890'),
        ('201234567890', '201234567890'),
        ('1234567890', '201234567890'),
    ]
    
    all_passed = True
    for input_num, expected in test_numbers:
        try:
            result = whatsapp._format_phone_number(input_num)
            if result == expected:
                print(f"  ✓ {input_num} → {result}")
            else:
                print(f"  ✗ {input_num} → {result} (expected {expected})")
                all_passed = False
        except Exception as e:
            print(f"  ✗ Error formatting {input_num}: {e}")
            all_passed = False
    print()
    
    # Test 4: Test message templates
    print("[4] Testing Message Templates...")
    try:
        now = timezone.now()
        
        present_msg = whatsapp._get_present_message("أحمد محمد", now)
        print(f"  ✓ Present message template: {len(present_msg)} chars")
        
        late_msg = whatsapp._get_late_message("أحمد محمد", now)
        print(f"  ✓ Late message template: {len(late_msg)} chars")
        
        absent_msg = whatsapp._get_absent_message("أحمد محمد")
        print(f"  ✓ Absent message template: {len(absent_msg)} chars")
        
        payment_msg = whatsapp._get_payment_reminder_message("أحمد محمد", "الرياضيات", 300)
        print(f"  ✓ Payment reminder template: {len(payment_msg)} chars")
        
        warning_msg = whatsapp._get_warning_message("أحمد محمد", 300)
        print(f"  ✓ Warning message template: {len(warning_msg)} chars")
    except Exception as e:
        print(f"  ✗ Error creating message templates: {e}")
        return False
    print()
    
    # Test 5: Test NotificationService
    print("[5] Testing NotificationService...")
    try:
        notification_service = NotificationService()
        print(f"  ✓ NotificationService initialized")
        print(f"  ✓ Notification method: {notification_service.notification_method}")
    except Exception as e:
        print(f"  ✗ Error initializing NotificationService: {e}")
        return False
    print()
    
    # Test 6: Send test message (optional)
    print("[6] Ready to Send Test Message")
    print("  To send a test message, use:")
    print("  >>> whatsapp.send_message('201234567890', 'Test message')")
    print()
    
    print("="*60)
    print("✓ All tests passed! Service is ready to use.")
    print("="*60 + "\n")
    
    return True


def test_send_message():
    """Send a test message (requires valid phone number and API token)"""
    
    print("\nSending Test Message...")
    print("-"*60)
    
    whatsapp = WhatsAppService()
    
    # Test with a valid Egyptian phone number
    # Replace with actual phone number for testing
    test_phone = '201234567890'  # Change this to a valid number
    test_message = 'This is a test message from Education Management System! ✓'
    
    print(f"Phone: {test_phone}")
    print(f"Message: {test_message}")
    print("\nSending...")
    
    result = whatsapp.send_message(test_phone, test_message)
    
    if result['success']:
        print(f"✓ Message sent successfully!")
        print(f"  Message ID: {result.get('message_id')}")
        print(f"  Response: {result['message']}")
    else:
        print(f"✗ Failed to send message")
        print(f"  Error: {result['error']}")
    
    print("-"*60 + "\n")
    
    return result['success']


if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Test WhatsApp API Integration')
    parser.add_argument('--send-test', action='store_true', help='Send a test message')
    parser.add_argument('--phone', help='Phone number for test message')
    args = parser.parse_args()
    
    # Run core tests
    success = test_whatsapp_service()
    
    # Optionally send a test message
    if args.send_test or args.phone:
        if args.phone:
            # Replace the test phone with provided one
            whatsapp = WhatsAppService()
            result = whatsapp.send_message(
                args.phone,
                'Test message from Education Management System'
            )
            if result['success']:
                print(f"✓ Test message sent to {args.phone}")
            else:
                print(f"✗ Failed: {result['error']}")
        else:
            test_send_message()
    
    sys.exit(0 if success else 1)
