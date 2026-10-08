"""
Playwright smoke test of the live site — run it through ``e2e/run_live.sh``.

Three passes, all read-only:

* **every page** in the sidebar (plus the detail pages behind them) loads with
  HTTP 200 and no JavaScript error;
* **every save button** of the features built for the desk (register notes,
  marking a lesson from the register, an excuse with its reason, cancelling a
  lesson, the scanner's override, the payment card's report link) is clicked —
  the request is caught in the browser, its payload checked, and a fake
  success returned so the page's own update can be checked too. Nothing
  reaches the server;
* **printing** — the register / student report / list print are rendered as
  print and must stay tables (a narrow print page used to turn every table
  into one card per row).

Exit code 1 if any check fails; screenshots of failures land in ``e2e/out/``.
"""
import json
import os
import sys
import traceback

from playwright.sync_api import sync_playwright

BASE = 'https://sys.educore.software'
OUT = os.path.join(os.path.dirname(__file__), 'out')
cfg = json.load(open(sys.argv[1]))
results = []


def check(part, ok, info=''):
    results.append((part, bool(ok), info))
    print(('✔' if ok else '✘'), part, ('— ' + str(info)) if info else '', flush=True)


def main():
    os.makedirs(OUT, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch()
        ctx = browser.new_context(viewport={'width': 1366, 'height': 900}, accept_downloads=True)
        ctx.add_cookies([{'name': cfg['cookie'], 'value': cfg['key'], 'domain': 'sys.educore.software',
                          'path': '/', 'secure': True, 'httpOnly': True}])
        page = ctx.new_page()
        errors, writes = [], []
        page.on('pageerror', lambda e: errors.append(str(e)[:150]))

        # ── Every write is intercepted: recorded, answered with a fake success ──
        fake = {'next': None}

        def route(r):
            req = r.request
            if req.method in ('GET', 'HEAD', 'OPTIONS'):
                return r.continue_()
            writes.append({'url': req.url, 'body': req.post_data or ''})
            body = fake['next'] or {'success': True}
            fake['next'] = None
            r.fulfill(status=200, content_type='application/json', body=json.dumps(body, ensure_ascii=False))
        page.route('**/*', route)
        page.on('dialog', lambda d: d.accept('سبب اختبار' if d.type == 'prompt' else None))

        def go(path):
            errors.clear()
            resp = page.goto(BASE + path, wait_until='networkidle', timeout=60000)
            return resp.status if resp else 0

        def run(part, fn):
            try:
                fn()
            except Exception as exc:  # noqa: BLE001
                check(part, False, f'{type(exc).__name__}: {str(exc)[:120]}')
                page.screenshot(path=os.path.join(OUT, f'{len(results)}.png'))
                traceback.print_exc(limit=1)

        g, sid = cfg['group_id'], cfg['student_id']

        # ── 1. every sidebar page ──
        def sidebar():
            go('/')
            links = sorted({a for a in page.eval_on_selector_all(
                '.sidebar a.menu-item[href]', 'els => els.map(e => e.getAttribute("href"))')
                if a and a.startswith('/') and 'logout' not in a})
            for href in links:
                st = go(href)
                check(f'صفحة {href}', st == 200 and not errors, f'{st} {errors[:1]}')
        run('صفحات القائمة', sidebar)

        details = [f'/students/{sid}/', f'/students/{sid}/report/', f'/teachers/groups/{g}/',
                   f'/reports/cycle-register/?group={g}', '/attendance/scanner/']
        if cfg.get('settlement_id'):
            details += [f'/payments/settlements/{cfg["settlement_id"]}/',
                        f'/payments/settlements/{cfg["settlement_id"]}/print/']
        for path in details:
            run(path, lambda path=path: check(f'صفحة {path}', go(path) == 200 and not errors, errors[:1]))

        # ── 2. features ──
        def scanner():
            go('/attendance/scanner/')
            page.wait_for_selector('#dayLogDate')
            page.wait_for_timeout(1500)
            n = page.locator('.day-row').count()
            check('المسح: سجل الحضور بالمجموعة (مش اللوحة القديمة)', page.locator('#filterAll').count() == 0,
                  f'{page.locator(".day-group").count()} مجموعة / {n} طالب')
            page.reload(wait_until='networkidle'); page.wait_for_timeout(1500)
            check('المسح: السجل باقي بعد الريفريش', page.locator('.day-row').count() == n)
            # a scan rejected as too early, for a student in several groups
            fake['next'] = {
                'success': False, 'error_type': 'too_early', 'severity': 'info', 'group_id': 2,
                'message': 'مبكر جداً! حصة الصف الاول — مستر اختبار للطالب طالب اختبار',
                'student_id': 1, 'student_name': 'طالب اختبار',
                'dossier': {'student_id': 1, 'full_name': 'طالب اختبار', 'student_code': '9', 'enrollments': [
                    {'group_id': 1, 'group_name': 'مجموعة أ', 'teacher_id': 1, 'teacher_name': 'مستر أ',
                     'schedule_day_ar': 'السبت', 'schedule_time': '14:00', 'financial_status': 'عادي',
                     'payment': {'status': 'paid', 'status_display': 'مدفوع', 'amount_due': 1, 'amount_paid': 1}},
                    {'group_id': 2, 'group_name': 'الصف الاول', 'teacher_id': 2, 'teacher_name': 'مستر اختبار',
                     'schedule_day_ar': 'الأحد', 'schedule_time': '16:30', 'financial_status': 'عادي',
                     'payment': {'status': 'paid', 'status_display': 'مدفوع', 'amount_due': 1, 'amount_paid': 1}}]}}
            box = page.locator('input[placeholder*="كود الطالب"]').first
            box.fill('9'); box.press('Enter')
            page.wait_for_selector('.dossier-target')
            check('المسح: المجموعة اللي اتمسح عليها متعلّمة', 'مستر اختبار' in page.locator('.dossier-target').inner_text())
            btn = page.locator('.scanner-actions button').first
            check('المسح: زرار التجاوز فيه المدرس والميعاد', 'مستر اختبار' in btn.inner_text() and '16:30' in btn.inner_text())
            writes.clear()
            fake['next'] = {'success': True, 'message': 'تم', 'attendance': {'status': 'present', 'status_display': 'حاضر'}}
            btn.click()
            page.wait_for_selector('text=تم التسجيل بتجاوز إداري')
            details_text = page.locator('#resultDetails').inner_text()
            check('المسح: بعد التجاوز بيقول دخل عند مين', 'مستر اختبار' in details_text and 'الصف الاول' in details_text)
            check('المسح: التجاوز بعت المجموعة الصح', any('"group_id":2' in w['body'].replace(' ', '') for w in writes))
        run('صفحة المسح', scanner)

        def students():
            go('/students/?search=' + cfg['student_code'])
            rows = page.locator('table tbody tr').count()
            check(f'بحث الطلاب بالكود {cfg["student_code"]}', rows == 1, f'{rows} صف')
        run('بحث الطلاب', students)

        def report():
            go(f'/students/{sid}/report/')
            check('تقرير الطالب: الحضور بالمجموعة', page.locator('.ghead').count() >= 1 and page.locator('.ghead').count() == page.locator('table.paper').count())
        run('تقرير الطالب', report)

        def payments():
            go('/payments/')
            check('المدفوعات: رابط كشف الطالب', page.locator('a[href*="/report/"]').count() > 0)
            check('المدفوعات: مافيش بيانات تجريبية', page.locator('text=TEST_CLAUDE').count() == 0)
        run('المدفوعات', payments)

        def register():
            go(f'/reports/cycle-register/?group={g}')
            check('كشف الدورة: الدورات تحت بعض', page.locator('.sheet').count() >= 1, f'{page.locator(".sheet").count()} دورة')
            # student note
            note = page.locator('input.note-in').first
            writes.clear(); note.fill('ملاحظة اختبار'); note.press('Enter'); page.wait_for_timeout(600)
            check('كشف الدورة: ملاحظة الطالب بتتبعت', any('cycle-register/note' in w['url'] and 'kind=student' in w['body'] for w in writes))
            # group note
            area = page.locator('textarea.note-in').first
            writes.clear(); area.fill('ملاحظة مجموعة اختبار'); area.evaluate('el => el.blur()'); page.wait_for_timeout(600)
            check('كشف الدورة: ملاحظة المجموعة بتتبعت', any('kind=cycle' in w['body'] for w in writes))
            # mark a lesson from the register
            cell = page.locator('td.editable').first
            cell.scroll_into_view_if_needed(); page.wait_for_timeout(200)
            writes.clear(); fake['next'] = {'success': True, 'attendance': {'status': 'present'}}
            cell.click(); page.locator('.cell-menu button', has_text='حاضر').click(); page.wait_for_timeout(600)
            check('كشف الدورة: تسجيل حاضر من الخانة', any('/api/manual/' in w['url'] and 'present' in w['body'] for w in writes)
                  and '/' in cell.inner_text(), cell.inner_text())
            writes.clear(); fake['next'] = {'success': True, 'attendance': {'status': 'exception'}}
            cell.click(); page.locator('.cell-menu button', has_text='عذر').click(); page.wait_for_timeout(600)
            check('كشف الدورة: العذر بيطلب السبب ويبعته', any('سبب اختبار' in w['body'] and 'exception' in w['body'] for w in writes))
            # cancel a lesson (no WhatsApp)
            if page.locator('.js-cancel').count():
                box = page.locator('.js-cancel').first.locator('xpath=..')
                box.locator('.js-cancel-date').fill(page.locator('td.editable').first.get_attribute('data-date'))
                box.locator('.js-cancel-reason').fill('سبب اختبار')
                writes.clear()
                with page.expect_navigation(wait_until='networkidle'):
                    page.locator('.js-cancel').first.click()
                w = [w for w in writes if 'cancel' in w['url']]
                check('كشف الدورة: إلغاء حصة بسبب ومن غير واتساب', w and 'notify=0' in w[0]['body'] and 'reason=' in w[0]['body'])
            with page.expect_download() as dl:
                page.click('text=Excel')
            check('كشف الدورة: تصدير Excel', dl.value.suggested_filename.endswith('.xlsx'), dl.value.suggested_filename)
        run('كشف الدورة', register)

        def group_page():
            go(f'/teachers/groups/{g}/')
            check('صفحة المجموعة: قائمة الدورات', page.locator('#grid-cycle option').count() >= 2)
            with page.expect_navigation(wait_until='networkidle'):
                page.select_option('#grid-cycle', index=min(1, page.locator('#grid-cycle option').count() - 2))
            check('صفحة المجموعة: تغيير الدورة بيغير الجدول', 'from=' in page.url)
            # default view: the paper sheet of the cycle, editable in place
            if page.locator('#paper-frame').count():
                page.locator('#paper-frame').scroll_into_view_if_needed(); page.wait_for_timeout(1500)
                fr = page.frame_locator('#paper-frame')
                check('صفحة المجموعة: كشف الورقة ظاهر', fr.locator('table.reg').first.is_visible())
                pc = fr.locator('td.editable').first
                if pc.count():
                    writes.clear(); fake['next'] = {'success': True, 'attendance': {'status': 'absent'}}
                    pc.click(); fr.locator('.cell-menu button', has_text='غائب').first.click(); page.wait_for_timeout(600)
                    check('صفحة المجموعة: خانة الورقة بتتسجل', any('"absent"' in w['body'] for w in writes) and pc.inner_text().strip() == 'غ',
                          pc.inner_text())
                page.locator('#grid-view-tabs button[data-view=classic]').click()
            cell = page.locator('.attendance-grid td.cell:not(.cell-cancelled):not([data-locked])').first
            if cell.count():
                cell.scroll_into_view_if_needed(); page.wait_for_timeout(300)
                writes.clear(); fake['next'] = {'success': True, 'attendance': {'status': 'exception'}}
                cell.click(); page.locator('.cell-chooser button', has_text='عذر').click(); page.wait_for_timeout(600)
                check('صفحة المجموعة: العذر بسببه', any('سبب اختبار' in w['body'] for w in writes) and 'سبب اختبار' in (cell.get_attribute('title') or ''))
            if cfg.get('exc_group'):
                go(f'/teachers/groups/{cfg["exc_group"]}/?from={cfg["exc_date"]}&to={cfg["exc_date"]}')
                check('صفحة المجموعة: ملاحظات الأعذار تحت الجدول', page.locator('.grid-notes li').count() >= 1)
        run('صفحة المجموعة', group_page)

        # ── settlement sheet: short dates side by side, unpaid marked ──
        if cfg.get('settlement_id'):
            def settlement():
                go(f'/payments/settlements/{cfg["settlement_id"]}/')
                h = page.evaluate('document.documentElement.scrollHeight')
                rows = page.locator('.settle-table tbody tr').count()
                check('التصفية: التواريخ مختصرة', page.locator('.settle-table .dates span').count() > 0
                      and page.locator('.settle-table td:has-text("2026-")').count() == 0)
                check('التصفية: الصف مش طويل', rows == 0 or h / rows < 140, f'{h}px / {rows} صف')
            run('التصفية', settlement)

        # ── 3. printing stays a table ──
        def printing():
            for path in (f'/reports/cycle-register/?group={g}', f'/teachers/groups/{g}/', f'/students/{sid}/report/',
                         '/reports/payments/?print=1'):
                go(path)
                page.emulate_media(media='print')
                disp = page.evaluate("(() => { const t = document.querySelector('tbody td'); return t ? getComputedStyle(t).display : 'none'; })()")
                page.emulate_media(media='screen')
                check(f'طباعة {path}: جدول مش كروت', disp in ('table-cell', 'none'), disp)
        run('الطباعة', printing)

        browser.close()

    failed = [r for r in results if not r[1]]
    print(f'\n{len(results) - len(failed)}/{len(results)} نجح')
    sys.exit(1 if failed else 0)


main()
