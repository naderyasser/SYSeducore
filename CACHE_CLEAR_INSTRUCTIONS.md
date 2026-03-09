# CACHE CLEAR INSTRUCTIONS
**Date**: 2026-02-10 15:06 UTC
**Status**: Services Restarted

---

## ✅ Server-Side Actions Completed

1. ✅ **Gunicorn**: Hard restart (stop → start)
2. ✅ **Nginx**: Hard restart (full restart)
3. ✅ **Static files**: Collected
4. ✅ **All services**: Running

---

## 🔄 Client-Side Cache Clear Required

The changes are deployed, but your browser has cached the old version. Please clear your browser cache:

### Chrome / Edge:
1. Press `Ctrl + Shift + Delete` (Windows) or `Cmd + Shift + Delete` (Mac)
2. Select "Cached images and files"
3. Click "Clear data"

**OR** Hard refresh:
- Press `Ctrl + F5` (Windows) or `Cmd + Shift + R` (Mac)

### Firefox:
1. Press `Ctrl + Shift + Delete`
2. Select "Cache"
3. Click "Clear Now"

**OR** Hard refresh:
- Press `Ctrl + Shift + R`

### Safari:
1. Press `Cmd + Option + E` to empty cache
2. Then press `Cmd + R` to reload

---

## 🚀 Quick Test (No Cache Clear Needed)

### Test in Incognito/Private Mode:
1. Open new **Incognito/Private window** (Ctrl + Shift + N)
2. Visit: https://sys.educore.software
3. Changes should be visible immediately

This bypasses cache and confirms the deployment worked.

---

## ✅ What Should Be Visible After Cache Clear:

### 1. Sidebar Menu:
- Hover over items - no cross-highlighting ✅

### 2. Teachers Bookings (`/teachers/bookings/`):
- Icons removed (no gender/graduation icons) ✅
- "عرض الكل" button works ✅
- Phone numbers clickable ✅
- "المواعيد و الحضور" section visible ✅

### 3. Calendar (`/teachers/bookings/calendar/`):
- "حجز موعد جديد" → goes to create form ✅

### 4. Attendance Scanner (`/attendance/scanner/`):
- Mode switching works ✅
- Camera controls work ✅

---

## 🔍 Verification Commands (Server-Side)

```bash
# Check services
sudo systemctl status gunicorn
sudo systemctl status nginx

# Both should show: Active: active (running)
```

**Result**:
```
Gunicorn: ● active (running) - PID 786936
Nginx:    ● active (running) - PID 787043
```

✅ **All services running with fresh code**

---

## 📝 Summary

**Server**: ✅ Fully restarted with all changes
**Client**: ⚠️ Needs browser cache clear

**Action Required**: Clear browser cache or test in Incognito mode

---

## 🆘 If Still Not Working:

1. **Verify you're on the right site**: https://sys.educore.software
2. **Check browser console** (F12) for errors
3. **Try different browser** to rule out browser-specific issues
4. **Check if using VPN/Proxy** that might cache content

---

## Status: ✅ DEPLOYED & READY

All changes are live on the server. Browser cache clear is the final step.
