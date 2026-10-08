"""
Screenshots of the main sheets on the LIVE site, on screen and as printed —
run through ``sh e2e/run_live.sh --shots``. Output in ``e2e/out/``.

Read-only like the other live scripts: every non-GET request is answered in
the browser with a fake success and never reaches the server.
"""
import json
import os
import subprocess
import sys

from playwright.sync_api import sync_playwright

BASE = 'https://sys.educore.software'
cfg = json.load(open(sys.argv[1]))
# SHOT_GROUP / SHOT_STUDENT / SHOT_CODE pick a fuller group than the default.
for k in ('group_id', 'student_id', 'student_code'):
    cfg[k] = os.environ.get('SHOT_' + k.split('_')[0].upper() if k != 'student_code' else 'SHOT_CODE', cfg[k])
OUT = os.path.join(os.path.dirname(__file__), 'out')
os.makedirs(OUT, exist_ok=True)


def main():
    g, sid, code = cfg['group_id'], cfg['student_id'], cfg['student_code']
    sheets = [
        ('1-كشف-الدورة', f'/reports/cycle-register/?group={g}'),
        ('2-جدول-المجموعة', f'/teachers/groups/{g}/'),
        ('3-تقرير-الطالب', f'/students/{sid}/report/'),
        ('4-المدفوعات', f'/payments/?search={code}'),
    ]
    if cfg.get('settlement_id'):
        sheets.append(('5-التصفية', f'/payments/settlements/{cfg["settlement_id"]}/'))
    made = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={'width': 1366, 'height': 900}, locale='ar-EG')
        ctx.add_cookies([{'name': cfg['cookie'], 'value': cfg['key'], 'domain': 'sys.educore.software',
                          'path': '/', 'secure': True, 'httpOnly': True}])
        page = ctx.new_page()
        page.route('**/*', lambda r: r.fulfill(status=200, content_type='application/json',
                                                body='{"success": true}')
                   if r.request.method not in ('GET', 'HEAD', 'OPTIONS') else r.continue_())

        def shot(name):
            path = os.path.join(OUT, name + '.png')
            page.screenshot(path=path, full_page=True)
            made.append(path)

        for name, url in sheets:
            page.goto(BASE + url, wait_until='networkidle', timeout=60000)
            frame = page.locator('#paper-frame')     # lazy iframe on the group page
            if frame.count():
                frame.scroll_into_view_if_needed()
                page.wait_for_load_state('networkidle')
                page.wait_for_timeout(1500)
            shot(name + '-شاشة')
            pdf = os.path.join(OUT, name + '-طباعة.pdf')
            page.pdf(path=pdf, prefer_css_page_size=True, print_background=True)
            stem = os.path.join(OUT, name + '-طباعة')
            subprocess.run(['pdftoppm', '-png', '-r', '70', '-f', '1', '-l', '2', pdf, stem], check=True)
            made += sorted(os.path.join(OUT, f) for f in os.listdir(OUT)
                           if f.startswith(name + '-طباعة') and f.endswith('.png'))

        # the new payment dialogs
        page.goto(BASE + f'/payments/?search={code}', wait_until='networkidle')
        btn = page.locator('button:has-text("خصم / مجاني / ملاحظة")').first
        if btn.count():
            btn.click(); page.wait_for_timeout(600)
            page.locator('#adjModal .modal-content').screenshot(path=os.path.join(OUT, '6-شباك-الخصم.png'))
            made.append(os.path.join(OUT, '6-شباك-الخصم.png'))
        page.goto(BASE + f'/students/{sid}/', wait_until='networkidle')
        btn = page.locator('button[onclick^="collectPayment"]').first
        if btn.count():
            btn.click(); page.wait_for_timeout(600)
            page.locator('#pmKindDiscount + label').click()
            page.wait_for_timeout(200)
            page.locator('#payModal .modal-content').screenshot(path=os.path.join(OUT, '7-شباك-الدفع.png'))
            made.append(os.path.join(OUT, '7-شباك-الدفع.png'))
        browser.close()
    print('\n'.join(made))


main()
