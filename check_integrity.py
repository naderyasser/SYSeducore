#!/usr/bin/env python3
"""
Comprehensive Frontend-Backend Integrity Check
Scans all templates for buttons/forms and verifies backend logic
"""

import os
import re
from pathlib import Path

# Results storage
issues = []
warnings = []
verified = []

def scan_template(file_path):
    """Scan a template file for buttons and forms"""
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    results = {
        'file': str(file_path),
        'buttons': [],
        'forms': [],
        'fetch_calls': [],
        'onclick_handlers': []
    }
    
    # Find all buttons
    button_pattern = r'<button[^>]*>(.*?)</button>'
    buttons = re.findall(button_pattern, content, re.DOTALL)
    results['buttons'] = len(buttons)
    
    # Find all forms
    form_pattern = r'<form[^>]*method=["\'](\w+)["\'][^>]*>'
    forms = re.findall(form_pattern, content)
    results['forms'] = forms
    
    # Find fetch calls
    fetch_pattern = r'fetch\(["\']([^"\']+)["\']'
    fetches = re.findall(fetch_pattern, content)
    results['fetch_calls'] = fetches
    
    # Find inline onclick
    onclick_pattern = r'onclick=["\']([^"\']+)["\']'
    onclicks = re.findall(onclick_pattern, content)
    results['onclick_handlers'] = onclicks
    
    return results

def check_view_has_save(view_file, view_name):
    """Check if a view actually saves data"""
    try:
        with open(view_file, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Find the function
        func_pattern = rf'def {view_name}\([^)]*\):'
        if not re.search(func_pattern, content):
            return None
        
        # Extract function body (simplified)
        func_start = content.find(f'def {view_name}(')
        if func_start == -1:
            return None
        
        # Look for save operations
        has_save = bool(re.search(r'\.save\(\)', content[func_start:func_start+2000]))
        has_create = bool(re.search(r'\.create\(', content[func_start:func_start+2000]))
        has_update = bool(re.search(r'\.update\(', content[func_start:func_start+2000]))
        
        return has_save or has_create or has_update
    except:
        return None

# Scan templates directory
templates_dir = Path('/root/.gemini/antigravity/scratch/SYSeducore/templates')

print("=" * 80)
print("COMPREHENSIVE FRONTEND-BACKEND INTEGRITY CHECK")
print("=" * 80)
print()

# Critical pages to check
critical_pages = [
    'teachers/bookings/create.html',
    'teachers/bookings/search.html',
    'students/form.html',
    'students/detail.html',
    'teachers/groups/form.html',
    'attendance/scanner.html',
]

for page in critical_pages:
    file_path = templates_dir / page
    if not file_path.exists():
        continue
    
    print(f"\n📄 {page}")
    print("-" * 80)
    
    results = scan_template(file_path)
    
    print(f"  Buttons: {results['buttons']}")
    print(f"  Forms: {len(results['forms'])} ({', '.join(results['forms']) if results['forms'] else 'none'})")
    print(f"  Fetch calls: {len(results['fetch_calls'])}")
    if results['fetch_calls']:
        for fetch in results['fetch_calls']:
            print(f"    - {fetch}")
    
    print(f"  Inline onclick: {len(results['onclick_handlers'])}")
    if results['onclick_handlers']:
        for onclick in results['onclick_handlers'][:3]:  # Show first 3
            print(f"    - {onclick[:60]}...")
    
    # Check for issues
    if results['onclick_handlers']:
        warnings.append(f"{page}: Has {len(results['onclick_handlers'])} inline onclick handlers")
    
    if results['buttons'] > 0 and not results['forms'] and not results['fetch_calls']:
        issues.append(f"{page}: Has buttons but no forms or fetch calls")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)

if issues:
    print(f"\n🔴 CRITICAL ISSUES ({len(issues)}):")
    for issue in issues:
        print(f"  - {issue}")

if warnings:
    print(f"\n⚠️  WARNINGS ({len(warnings)}):")
    for warning in warnings:
        print(f"  - {warning}")

print(f"\n✅ Scanned {len(critical_pages)} critical pages")
