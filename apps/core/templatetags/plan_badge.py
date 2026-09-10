"""
``{% plan_badge student %}`` — the one place the "باقة 5 مواد" badge is drawn.

A bundle student must be recognisable wherever their name appears (accounts,
payment, attendance, the scanner), and the badge must look the same on all
of them. Renders nothing for a regular student, so it can sit next to every
name unconditionally.
"""
from django import template
from django.utils.html import format_html

register = template.Library()

BADGE_CLASS = 'plan-badge plan-badge-bundle'


@register.simple_tag
def plan_badge(student, extra_class=''):
    label = getattr(student, 'plan_badge_label', '')
    if not label:
        return ''
    return format_html(
        '<span class="{} {}" title="خطة الاشتراك: {}"><i class="bi bi-box-seam"></i> {}</span>',
        BADGE_CLASS, extra_class, label, label,
    )
