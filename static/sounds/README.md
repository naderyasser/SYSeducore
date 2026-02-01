# Sound Effects for Attendance System

This directory contains audio feedback sounds for the QR code attendance kiosk.

## Files

- `success.mp3` - Played when a student successfully scans in (green screen)
- `error.mp3` - Played when attendance is blocked (red/yellow/white screens)

## Usage

The sounds are automatically played by the kiosk scanner when:
1. A QR code is successfully scanned and processed
2. Manual entry is submitted
3. The server returns a result

## Audio Properties

- Format: MP3
- Volume: 50% (adjustable in JavaScript)
- Duration: ~0.5 seconds
- Purpose: Quick audio feedback for kiosk operators

## Browser Compatibility

The sounds use the Web Audio API and should work in all modern browsers:
- Chrome/Edge 88+
- Firefox 85+
- Safari 14+
- Mobile browsers (iOS Safari, Chrome Mobile)

Note: Browsers may block auto-play until user interaction occurs. The kiosk scanner handles this by playing sounds only after user interaction (camera permission or manual input).
