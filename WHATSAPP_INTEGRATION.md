# WhatsApp API Integration Guide

## WASender API Integration

Your Education Management System is now integrated with **WASender API** for sending WhatsApp messages.

### Configuration

The following settings have been added to `config/settings.py`:

```python
WASENDER_API_TOKEN = config('WASENDER_API_TOKEN', default='dc40a76959c63ba6acb5d8f2e3424d424e31b476150479ae2fdc5a72398671cc')
WASENDER_API_URL = config('WASENDER_API_URL', default='https://wasenderapi.com/api/send-message')
```

### API Token

- **Token**: `dc40a76959c63ba6acb5d8f2e3424d424e31b476150479ae2fdc5a72398671cc`
- **Endpoint**: `https://wasenderapi.com/api/send-message`
- **Auth Method**: Bearer Token (Authorization header)

### Features

The `WhatsAppService` class supports:

1. **Single Message Sending**
   - Send individual WhatsApp messages
   - Automatic phone number formatting for Egyptian numbers
   - Error handling and logging

2. **Bulk Messaging**
   - Send messages to multiple recipients
   - Summarized results with success/failure counts

3. **Group Messages**
   - Send messages to WhatsApp groups
   - Same error handling as individual messages

4. **Pre-built Notification Templates**
   - Attendance notifications (present, late, absent)
   - Payment reminders
   - Warning messages before blocking
   - Block notifications

### Usage Examples

#### Sending a Single Message

```python
from apps.notifications.services import WhatsAppService

whatsapp = WhatsAppService()
result = whatsapp.send_message(
    to='201234567890',  # Egyptian phone number
    message='Hello, this is a test message!'
)

if result['success']:
    print(f"Message sent! ID: {result['message_id']}")
else:
    print(f"Error: {result['error']}")
```

#### Sending Attendance Notification

```python
from apps.notifications.services import NotificationService
from django.utils import timezone

service = NotificationService()
result = service.send_attendance_notification(
    student_name='محمد أحمد',
    parent_phone='201234567890',
    status='present',
    time=timezone.now()
)
```

#### Sending Payment Reminder

```python
from apps.notifications.services import NotificationService

service = NotificationService()
result = service.send_monthly_reminder(
    student_name='محمد أحمد',
    parent_phone='201234567890',
    group_name='الرياضيات',
    amount=300
)
```

### Phone Number Format

The service automatically formats phone numbers:
- Converts `01234567890` to `201234567890` (adds Egypt country code)
- Accepts numbers with or without leading `+` or `0`
- Accepts with or without country code

### Error Handling

All methods return a dictionary with:
- `success`: Boolean indicating if the operation succeeded
- `message_id`: The message ID from the API (if successful)
- `message`: Success message in Arabic
- `error`: Error description (if failed)

### API Request Format

The service sends requests in this format:

```bash
curl -X POST "https://wasenderapi.com/api/send-message" \
  -H "Authorization: Bearer dc40a76959c63ba6acb5d8f2e3424d424e31b476150479ae2fdc5a72398671cc" \
  -H "Content-Type: application/json" \
  -d '{"to": "+201234567890", "text": "Hello!"}'
```

### Environment Configuration

You can override the defaults by setting environment variables in your `.env` file:

```
WASENDER_API_TOKEN=your_token_here
WASENDER_API_URL=https://wasenderapi.com/api/send-message
```

### Troubleshooting

1. **Messages not sending**: Check that the token is correct and the API endpoint is accessible
2. **Connection timeout**: Verify network connectivity and API service status
3. **Invalid phone numbers**: Ensure phone numbers include country code (20 for Egypt)
4. **401 Unauthorized**: Verify the authorization token is correctly configured

### API Response Examples

**Success Response:**
```json
{
  "success": true,
  "message_id": "msg_123456",
  "status": "sent"
}
```

**Error Response:**
```json
{
  "success": false,
  "error": "Invalid phone number",
  "message": "The phone number format is invalid"
}
```

### Security Notes

- Never commit the token to version control
- Store the token in environment variables or `.env` files (which should be in `.gitignore`)
- Use the `.env.example` file as a template for team members
- Rotate tokens periodically in production

### Integration Points

The WhatsApp service is integrated with:
- **Attendance System**: Sends notifications when students arrive
- **Payment System**: Sends reminders and warnings
- **Student Management**: Sends barcode links via WhatsApp
- **Group Management**: Supports group notifications

### Testing

To test the integration:

```python
python manage.py shell

from apps.notifications.services import WhatsAppService
from django.utils import timezone

whatsapp = WhatsAppService()

# Test sending a message
result = whatsapp.send_message('201234567890', 'Test message')
print(result)
```

For more details, see the implementation in `apps/notifications/services.py`.
