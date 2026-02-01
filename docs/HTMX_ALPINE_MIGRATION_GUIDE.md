# HTMX + Alpine.js Migration Guide
## EDUCORE V2 Frontend Refactoring

This guide explains how to migrate from Vanilla JavaScript MVC to HTMX + Alpine.js for better maintainability.

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Project Structure](#project-structure)
3. [Installation](#installation)
4. [Key Concepts](#key-concepts)
5. [Component Examples](#component-examples)
6. [HTMX Patterns](#htmx-patterns)
7. [Alpine.js Patterns](#alpinejs-patterns)
8. [Migration Checklist](#migration-checklist)

---

## 🎯 Overview

### Why HTMX + Alpine.js?

| Feature | Vanilla JS MVC | HTMX + Alpine.js |
|---------|----------------|------------------|
| **Learning Curve** | High (custom MVC) | Low (declarative) |
| **Code Lines** | ~500+ | ~200 |
| **Server Round-trips** | Manual fetch | Automatic (HTMX) |
| **State Management** | Custom | Built-in (Alpine) |
| **Template Updates** | Manual DOM | HTML-based |
| **RTL Support** | Manual | Bootstrap RTL |

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Browser (Client)                          │
├─────────────────────────────────────────────────────────────┤
│  Alpine.js (State Management)                                │
│  ├── x-data: Component state                                │
│  ├── x-init: Initialization                                 │
│  ├── x-show/x-if: Conditional rendering                     │
│  └── @event: Event handlers                                 │
│                                                             │
│  HTMX (Server Communication)                                 │
│  ├── hx-get/hx-post: API calls                              │
│  ├── hx-target: Update target                               │
│  ├── hx-swap: Swap strategy                                 │
│  └── hx-indicator: Loading states                           │
└─────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                    Django Server                             │
├─────────────────────────────────────────────────────────────┤
│  htmx_views.py: Return HTML fragments                       │
│  ├── api_scan(): Process barcode                            │
│  ├── api_session_attendance(): Get attendance list          │
│  └── api_today_sessions(): Get sessions                     │
│                                                             │
│  Partials/: Reusable HTML fragments                         │
│  ├── scan_result_success.html                               │
│  ├── scan_result_error.html                                 │
│  └── attendance_rows.html                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## 📁 Project Structure

```
EDUCORE/
├── templates/
│   ├── base.html                 # Main template with CDN links
│   ├── partials/
│   │   ├── navbar.html           # Navigation component
│   │   └── footer.html           # Footer component
│   ├── attendance/
│   │   ├── scanner.html          # Scanner page (HTMX + Alpine)
│   │   ├── scanner_select.html   # Session selection page
│   │   └── partials/
│   │       ├── scan_result_success.html
│   │       ├── scan_result_error.html
│   │       └── attendance_rows.html
│   ├── reports/
│   │   └── dashboard.html        # Dashboard (HTMX + Alpine)
│   └── payments/
│       └── list.html             # Payments list (HTMX + Alpine)
│
├── static/
│   ├── css/
│   │   └── main.css              # RTL support + animations
│   └── js/
│       └── main.js               # Alpine.js components
│
└── apps/
    └── attendance/
        ├── views.py              # Traditional views
        ├── htmx_views.py         # HTMX-specific views
        └── urls.py               # URL configuration
```

---

## 🚀 Installation

### 1. Update `base.html`

The base template already includes all necessary CDN links:

```html
<!-- Bootstrap 5.3 RTL -->
<link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/css/bootstrap.rtl.min.css">

<!-- HTMX -->
<script src="https://unpkg.com/htmx.org@1.9.11"></script>

<!-- Alpine.js -->
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.13.3/dist/cdn.min.js">
```

### 2. Update `requirements.txt` (No changes needed!)

HTMX and Alpine.js are loaded via CDN, so no Python packages are required.

---

## 🔑 Key Concepts

### HTMX Attributes

| Attribute | Purpose | Example |
|-----------|---------|---------|
| `hx-get` | Make GET request | `hx-get="/api/data/"` |
| `hx-post` | Make POST request | `hx-post="/api/submit/"` |
| `hx-target` | Element to update | `hx-target="#result"` |
| `hx-swap` | How to update | `hx-swap="innerHTML"` |
| `hx-trigger` | When to trigger | `hx-trigger="click"` |
| `hx-indicator` | Loading element | `hx-indicator="#loading"` |

### Alpine.js Directives

| Directive | Purpose | Example |
|-----------|---------|---------|
| `x-data` | Component state | `x-data="{ count: 0 }"` |
| `x-init` | Initialize | `x-init="init()"` |
| `x-show` | Show/hide | `x-show="isOpen"` |
| `x-if` | Conditional | `x-if="user.loggedIn"` |
| `x-for` | Loop | `x-for="item in items"` |
| `@click` | Click handler | `@click="count++"` |
| `x-model` | Two-way binding | `x-model="query"` |

---

## 💡 Component Examples

### 1. Scanner Component

```html
<div x-data="scannerData()" x-init="init()">
    <!-- Form with HTMX -->
    <form hx-post="{% url 'attendance:htmx_api_scan' %}"
          hx-target="#scan-result"
          hx-indicator="#scan-indicator">
        
        <input type="text" name="barcode" x-model="barcode" required>
        <button type="submit">Scan</button>
    </form>
    
    <!-- Result area -->
    <div id="scan-result"></div>
</div>
```

```javascript
function scannerData() {
    return {
        barcode: '',
        init() {
            this.$nextTick(() => {
                this.$refs.barcodeInput?.focus();
            });
        }
    };
}
```

### 2. Toast Notifications

```html
<div x-data="appData()">
    <div class="toast-container">
        <template x-for="toast in toasts" :key="toast.id">
            <div class="toast" :class="'toast-' + toast.type">
                <span x-text="toast.message"></span>
            </div>
        </template>
    </div>
</div>
```

```javascript
function appData() {
    return {
        toasts: [],
        showToast(message, type = 'info') {
            this.toasts.push({ id: Date.now(), message, type });
        }
    };
}
```

---

## 🔄 HTMX Patterns

### Pattern 1: Optimistic Updates

```html
<div id="stats" 
     hx-get="/api/stats/" 
     hx-trigger="load, every 5s"
     hx-swap="innerHTML">
    Loading...
</div>
```

### Pattern 2: Form Submission

```html
<form hx-post="/api/submit/" 
      hx-target="#result" 
      hx-swap="innerHTML">
    <input name="data" required>
    <button type="submit">Submit</button>
</form>
<div id="result"></div>
```

### Pattern 3: Infinite Scroll

```html
<div id="items"
     hx-get="/api/items/?page=1"
     hx-trigger="load"
     hx-swap="outerHTML">
    <!-- Items loaded here -->
</div>
```

---

## ⚡ Alpine.js Patterns

### Pattern 1: Search with Autocomplete

```html
<div x-data="studentSearchData()">
    <input type="search" 
           x-model="query" 
           @input.debounce.500ms="search()">
    
    <div class="dropdown" x-show="results.length > 0">
        <template x-for="student in results" :key="student.id">
            <div @click="selectStudent(student)">
                <span x-text="student.name"></span>
            </div>
        </template>
    </div>
</div>
```

### Pattern 2: Modal Dialog

```html
<div x-data="{ isOpen: false }">
    <button @click="isOpen = true">Open</button>
    
    <div x-show="isOpen" 
         x-transition:enter="transition ease-out"
         x-transition:enter-start="opacity-0"
         x-transition:enter-end="opacity-100">
        <div class="modal">
            <button @click="isOpen = false">Close</button>
        </div>
    </div>
</div>
```

### Pattern 3: Real-time Stats

```html
<div x-data="statsData()" x-init="init(); setInterval(refresh, 5000)">
    <span x-text="stats.total"></span>
    <span x-text="stats.present"></span>
</div>
```

---

## ✅ Migration Checklist

### Phase 1: Setup (Completed ✅)

- [x] Update `base.html` with CDN links
- [x] Create `main.js` with Alpine.js components
- [x] Create `main.css` with RTL support
- [x] Create partial templates (navbar, footer)

### Phase 2: Scanner (Completed ✅)

- [x] Create `scanner.html` with HTMX + Alpine.js
- [x] Create `htmx_views.py` with HTML fragment responses
- [x] Create partial templates for scan results
- [x] Update URLs for HTMX endpoints

### Phase 3: Dashboard (Completed ✅)

- [x] Create `dashboard.html` with HTMX + Alpine.js
- [x] Add real-time stats loading
- [x] Add session list with HTMX

### Phase 4: Payments (Completed ✅)

- [x] Create `payments/list.html` with HTMX + Alpine.js
- [x] Add filter functionality
- [x] Add pagination with HTMX

### Phase 5: Remaining Pages (TODO)

- [ ] Migrate student list page
- [ ] Migrate teacher list page
- [ ] Migrate reports pages
- [ ] Remove old MVC JavaScript files

---

## 📝 Best Practices

### 1. HTMX Best Practices

```html
<!-- ✅ Good: Use hx-indicator for loading states -->
<button hx-post="/api/submit">
    <span class="htmx-indicator">
        <span class="spinner-border"></span>
    </span>
    Submit
</button>

<!-- ❌ Bad: Manual loading states -->
<button onclick="showLoading(); submit();">Submit</button>
```

### 2. Alpine.js Best Practices

```javascript
// ✅ Good: Use x-data for component state
<div x-data="{ count: 0 }">
    <button @click="count++">+</button>
    <span x-text="count"></span>
</div>

// ❌ Bad: Global state
let count = 0;
function increment() { count++; }
```

### 3. RTL Support

```css
/* ✅ Good: Use Bootstrap RTL classes */
<div class="text-end">Right-aligned text</div>

/* ❌ Bad: Manual RTL handling */
<div style="text-align: right;">Right-aligned text</div>
```

---

## 🐛 Troubleshooting

### Issue: HTMX requests not working

**Solution:** Check that HTMX is loaded and the endpoint returns HTML (not JSON).

```python
# ✅ Good: Return HTML
def api_scan(request):
    html = render_to_string('partials/result.html', {'data': data})
    return HttpResponse(html)

# ❌ Bad: Return JSON
def api_scan(request):
    return JsonResponse({'data': data})
```

### Issue: Alpine.js not initializing

**Solution:** Ensure `defer` attribute is on the script tag.

```html
<!-- ✅ Good -->
<script defer src="https://cdn.jsdelivr.net/npm/alpinejs@3.13.3/dist/cdn.min.js"></script>

<!-- ❌ Bad -->
<script src="https://cdn.jsdelivr.net/npm/alpinejs@3.13.3/dist/cdn.min.js"></script>
```

---

## 📚 Additional Resources

- [HTMX Documentation](https://htmx.org/docs/)
- [Alpine.js Documentation](https://alpinejs.dev/)
- [Bootstrap RTL](https://getbootstrap.com/docs/5.3/getting-started/rtl/)
- [Django HTMX Patterns](https://django-htmx.readthedocs.io/)
