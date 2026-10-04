"""
Click every button on every page of the live site — run through
``sh e2e/run_live.sh --buttons``.

Safety, in the browser, before anything reaches the server:

* every non-GET request (save, delete, send, approve…) is answered with a fake
  ``{"success": true}`` and never sent;
* every GET whose path names an action (delete, toggle, cancel, logout, send,
  approve, restore, pay…) is aborted too — some of those views act on GET;
* confirm/prompt dialogs are accepted, so the click goes all the way to its
  final request, which is then caught by the two rules above.

A page fails if a click raises a JavaScript error or any request it makes
returns HTTP 5xx.
"""
import json
import os
import re
import sys

from playwright.sync_api import sync_playwright

BASE = 'https://sys.educore.software'
cfg = json.load(open(sys.argv[1]))
MAX_PER_PAGE = 60
RISKY_GET = re.compile(
    r'/(delete|toggle|toggle-status|logout|cancel|cancel-lesson|cancel-session|approve|reopen|restore|'
    r'restore-lesson|send|bulk|bulk-action|bulk-message|mark-paid|record|scanner-pay-now|pay-now|'
    r'remove|remove-from-group|refresh|build|wipe|reset|clear|empty|grace)(/|-|\b)', re.I)
# Everything clickable outside the sidebar / top bar: buttons and link-buttons
# (``a.btn`` — a link styled as an action, e.g. «طباعة» or «تعديل»).
_OUT = ':not(.sidebar *):not(.top-header *):not(.sidebar-overlay)'
BUTTONS = ', '.join(f'{sel}{_OUT}' for sel in (
    'button', '[role="button"]', 'input[type="submit"]', 'input[type="button"]', 'a.btn'))


def main():
    results, blocked = [], []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
        ctx.add_cookies([{'name': cfg['cookie'], 'value': cfg['key'], 'domain': 'sys.educore.software',
                          'path': '/', 'secure': True, 'httpOnly': True}])
        page = ctx.new_page()
        errors = []
        page.on('pageerror', lambda e: errors.append('JS: ' + str(e)[:140]))
        page.on('response', lambda r: errors.append(f'HTTP {r.status} {r.url[len(BASE):][:80]}')
                if r.status >= 500 and r.url.startswith(BASE) else None)
        page.on('dialog', lambda d: d.accept('اختبار' if d.type == 'prompt' else None))
        page.on('popup', lambda pop: pop.close())

        def route(r):
            req = r.request
            path = req.url[len(BASE):] if req.url.startswith(BASE) else ''
            if req.method not in ('GET', 'HEAD', 'OPTIONS'):
                return r.fulfill(status=200, content_type='application/json', body='{"success": true}')
            if path and RISKY_GET.search(path.split('?')[0]):
                blocked.append(path[:80])
                return r.abort()
            return r.continue_()
        page.route('**/*', route)

        def go(path):
            page.goto(BASE + path, wait_until='networkidle', timeout=60000)

        go('/')
        pages = sorted({a for a in page.eval_on_selector_all(
            '.sidebar a.menu-item[href]', 'els => els.map(e => e.getAttribute("href"))')
            if a and a.startswith('/') and 'logout' not in a})
        g, sid = cfg['group_id'], cfg['student_id']
        pages += [f'/students/{sid}/', f'/students/{sid}/report/', f'/teachers/groups/{g}/',
                  f'/reports/cycle-register/?group={g}']
        if cfg.get('settlement_id'):
            pages.append(f'/payments/settlements/{cfg["settlement_id"]}/')

        links = set()
        for path in pages:
            errors.clear()
            go(path)
            # Link-buttons that only open another page are checked once each by
            # address (below) instead of clicked and reloaded — far less load.
            for href in page.eval_on_selector_all(
                    'a.btn[href]' + _OUT, 'els => els.map(e => e.getAttribute("href"))'):
                if href and href.startswith('/') and not href.startswith('//'):
                    links.add(href.split('#')[0])
            total = page.locator(BUTTONS).count()
            clicked, labels = 0, []
            for i in range(min(total, MAX_PER_PAGE)):
                if page.url.split('#')[0] != (BASE + path).split('#')[0]:
                    go(path)            # the last click navigated away — come back
                btn = page.locator(BUTTONS).nth(i)
                try:
                    if not btn.is_visible() or not btn.is_enabled():
                        continue
                    href = btn.get_attribute('href')
                    if href and href.startswith('/') and not btn.get_attribute('onclick'):
                        continue    # plain navigation — covered by the link check
                    label = (btn.inner_text(timeout=1000) or btn.get_attribute('title') or btn.get_attribute('aria-label') or '?').strip()[:25]
                    btn.click(timeout=3000, no_wait_after=True)
                    page.wait_for_timeout(500)
                    page.keyboard.press('Escape')
                    clicked += 1
                    labels.append(label.replace('\n', ' '))
                except Exception:   # noqa: BLE001 — covered/detached/moved: not a site error
                    continue
            ok = not errors
            results.append((path, ok, clicked, total, errors[:3]))
            print(('✔' if ok else '✘'), path, f'— ضغط {clicked} زرار من {total}',
                  ('' if ok else f'| {errors[:3]}'), flush=True)
        # Every link-button's target page, once: must not be a server error.
        bad_links = []
        for href in sorted(links):
            if RISKY_GET.search(href.split('?')[0]):
                blocked.append(href)
                continue
            r = ctx.request.get(BASE + href, max_redirects=5)
            if r.status >= 500:
                bad_links.append(f'{r.status} {href}')
        ok = not bad_links
        results.append(('روابط الأزرار', ok, len(links), len(links), bad_links[:5]))
        print(('✔' if ok else '✘'), f'روابط الأزرار — {len(links)} رابط اتفتح', ('' if ok else f'| {bad_links[:5]}'), flush=True)
        browser.close()

    failed = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(failed)}/{len(results)} صفحة من غير أخطاء — '
          f'{sum(r[2] for r in results)} زرار اتضغط، {len(set(blocked))} طلب خطر اتمنع')
    sys.exit(1 if failed else 0)


main()
