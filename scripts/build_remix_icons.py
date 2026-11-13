"""
Build and organize official Remix Icons into the central icon system.
Generates:
1. bot/web/static/img/icons/*.svg (Official Remix Icon SVGs with theme gradients)
2. bot/web/static/img/icons/icons.json (Registry of icons, categories, and Remix origins)
3. bot/web/static/img/icons/README.md (Icon System Specification based on icon-system skill)
"""

import os
import re
import json

REMIX_MAPPINGS = {
    # 1. Navigation
    'dashboard': 'System/dashboard-fill.svg',
    'reports': 'Business/bar-chart-2-fill.svg',
    'shop': 'Finance/shopping-bag-3-fill.svg',
    'wallet': 'Finance/wallet-3-fill.svg',
    'profile': 'User & Faces/user-3-fill.svg',
    
    # 2. Main Sections & Admin Nav
    'settings': 'System/settings-3-fill.svg',
    'users': 'User & Faces/team-fill.svg',
    'nodes': 'Device/server-fill.svg',
    'finance': 'Finance/money-dollar-circle-fill.svg',
    'plans': 'Business/archive-stack-fill.svg',
    'package': 'Business/archive-stack-fill.svg',
    
    # 3. Actions & Status
    'zap': 'Weather/flashlight-fill.svg',
    'lightning': 'Weather/flashlight-fill.svg',
    'shield': 'System/shield-check-fill.svg',
    'lock-shield': 'System/shield-keyhole-fill.svg',
    'lock_shield': 'System/shield-keyhole-fill.svg',
    'rocket': 'Map/rocket-2-fill.svg',
    'gift': 'Finance/gift-2-fill.svg',
    'cart': 'Finance/shopping-cart-2-fill.svg',
    'trophy': 'Finance/trophy-fill.svg',
    'award': 'Business/award-fill.svg',
    'crown': 'Finance/vip-crown-2-fill.svg',
    'diamond': 'Finance/vip-diamond-fill.svg',
    'star': 'System/star-fill.svg',
    'sparkles': 'Weather/sparkling-2-fill.svg',
    'flame': 'Weather/fire-fill.svg',
    'clock': 'System/time-fill.svg',
    'calendar': 'Business/calendar-2-fill.svg',
    'copy': 'Document/file-copy-2-fill.svg',
    'check': 'System/checkbox-circle-fill.svg',
    'cross': 'System/close-circle-fill.svg',
    'warning': 'System/error-warning-fill.svg',
    'ban': 'System/forbid-2-fill.svg',
    'trash': 'System/delete-bin-6-fill.svg',
    'edit': 'Design/edit-2-fill.svg',
    'plus': 'System/add-line.svg',
    'search': 'System/search-2-line.svg',
    'globe': 'Business/global-fill.svg',
    'link': 'Editor/link-m.svg',
    'key': 'Others/key-2-fill.svg',
    'phone': 'Device/smartphone-fill.svg',
    'desktop': 'Device/computer-fill.svg',
    'antenna': 'Media/broadcast-fill.svg',
    'signal': 'Device/signal-cellular-3-fill.svg',
    'wifi': 'Device/wifi-fill.svg',
    'chat': 'Communication/chat-3-fill.svg',
    'support': 'Business/customer-service-2-fill.svg',
    'ticket': 'Finance/coupon-3-fill.svg',
    'cake': 'Food/cake-3-fill.svg',
    'receipt': 'Document/bill-fill.svg',
    'coins': 'Finance/coin-fill.svg',
    'credit-card': 'Finance/bank-card-2-fill.svg',
    'credit_card': 'Finance/bank-card-2-fill.svg',
    'sun': 'Weather/sun-fill.svg',
    'moon': 'Weather/moon-clear-fill.svg',
    'sunrise': 'Weather/sun-cloudy-fill.svg',
    'sunset': 'Weather/sun-cloudy-fill.svg',
    'sync': 'System/refresh-line.svg',
    'inbox': 'Business/inbox-archive-fill.svg',
    'download': 'System/download-2-fill.svg',
    'database': 'Device/database-2-fill.svg',
    'wheel': 'Device/gamepad-fill.svg',
    'qr': 'Device/qr-code-fill.svg',
    'layers': 'Business/stack-fill.svg',
    'route': 'Map/route-fill.svg',
    'recycle': 'Others/recycle-fill.svg',
    'lightbulb': 'Others/lightbulb-flash-fill.svg',
    'medal-gold': 'Business/medal-fill.svg',
    'medal-silver': 'Business/medal-2-fill.svg',
    'medal-bronze': 'Business/medal-line.svg',
    'medal_gold': 'Business/medal-fill.svg',
    'medal_silver': 'Business/medal-2-fill.svg',
    'medal_bronze': 'Business/medal-line.svg',
}

# Thematic gradients tailored for Telegram Mini Apps
COLOR_THEMES = {
    'dashboard': ('#38bdf8', '#0284c7'),       # Azure Sky
    'reports': ('#a78bfa', '#6366f1'),         # Purple / Indigo
    'shop': ('#34d399', '#059669'),            # Emerald Green
    'wallet': ('#fbbf24', '#d97706'),          # Amber Gold
    'profile': ('#38bdf8', '#2563eb'),         # Royal Azure
    
    'zap': ('#fbbf24', '#f59e0b'),             # Electric Amber
    'lightning': ('#fbbf24', '#f59e0b'),
    'shield': ('#38bdf8', '#0284c7'),          # Cyan Shield
    'lock-shield': ('#38bdf8', '#0284c7'),
    'lock_shield': ('#38bdf8', '#0284c7'),
    'rocket': ('#f43f5e', '#be123c'),          # Rose Rocket
    'gift': ('#ec4899', '#be185d'),            # Pink Gift
    'cart': ('#34d399', '#059669'),            # Emerald Cart
    'trophy': ('#fbbf24', '#d97706'),          # Golden Trophy
    'award': ('#fbbf24', '#d97706'),
    'crown': ('#fbbf24', '#d97706'),           # Gold Crown
    'diamond': ('#38bdf8', '#2563eb'),         # Blue Diamond
    'star': ('#fbbf24', '#f59e0b'),            # Gold Star
    'sparkles': ('#f472b6', '#c084fc'),        # Magic Sparkles
    'flame': ('#fb923c', '#ea580c'),           # Warm Flame
    'check': ('#34d399', '#10b981'),           # Emerald Check
    'cross': ('#f87171', '#ef4444'),           # Crimson Cross
    'warning': ('#fbbf24', '#f59e0b'),         # Amber Warning
    'ban': ('#f87171', '#ef4444'),             # Red Ban
    'cake': ('#f472b6', '#db2777'),            # Birthday Pink
    'ticket': ('#fbbf24', '#d97706'),          # Coupon Gold
    'coins': ('#fbbf24', '#d97706'),
    'credit-card': ('#38bdf8', '#0284c7'),
    'credit_card': ('#38bdf8', '#0284c7'),
    'medal-gold': ('#fbbf24', '#d97706'),
    'medal-silver': ('#94a3b8', '#64748b'),
    'medal-bronze': ('#d97706', '#92400e'),
    'medal_gold': ('#fbbf24', '#d97706'),
    'medal_silver': ('#94a3b8', '#64748b'),
    'medal_bronze': ('#d97706', '#92400e'),
    'sun': ('#fbbf24', '#f59e0b'),
    'moon': ('#818cf8', '#6366f1'),
    'sunrise': ('#fb923c', '#ea580c'),
    'sunset': ('#f43f5e', '#be123c'),
    'users': ('#38bdf8', '#2563eb'),
    'nodes': ('#38bdf8', '#0284c7'),
    'finance': ('#34d399', '#059669'),
    'package': ('#38bdf8', '#2563eb'),
    'plans': ('#a78bfa', '#6366f1'),
    'wheel': ('#ec4899', '#8b5cf6'),
    'chat': ('#38bdf8', '#0284c7'),
    'support': ('#38bdf8', '#0284c7'),
    'phone': ('#38bdf8', '#0284c7'),
}

output_dir = os.path.join('bot', 'web', 'static', 'img', 'icons')
os.makedirs(output_dir, exist_ok=True)

manifest = {}
built_count = 0

for name, rel_path in REMIX_MAPPINGS.items():
    src_path = os.path.join('node_modules', 'remixicon', 'icons', rel_path.replace('/', os.sep))
    if not os.path.exists(src_path):
        print(f"ERROR: missing {src_path}")
        continue
    
    with open(src_path, 'r', encoding='utf-8') as f:
        src_content = f.read()
    
    d_matches = re.findall(r'<path\s+d="([^"]+)"', src_content)
    if not d_matches:
        continue
    
    grad_id = f"ri_{name.replace('-', '_')}"
    theme_colors = COLOR_THEMES.get(name)
    
    if theme_colors:
        c1, c2 = theme_colors
    else:
        # Crisp silver-slate for tools, hardware, controls
        c1, c2 = '#e2e8f0', '#94a3b8'
        
    fill_def = f'''<defs>
    <linearGradient id="{grad_id}" x1="2" y1="2" x2="22" y2="22" gradientUnits="userSpaceOnUse">
      <stop stop-color="{c1}"/>
      <stop offset="1" stop-color="{c2}"/>
    </linearGradient>
  </defs>'''
    fill_val = f"url(#{grad_id})"
    paths_str = '\n    '.join([f'<path fill="{fill_val}" d="{d}"/>' for d in d_matches])
    
    svg_content = f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  {fill_def}
  <g fill="none">
    {paths_str}
  </g>
</svg>'''

    out_file = os.path.join(output_dir, f"{name}.svg")
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    
    manifest[name] = {
        'remix_source': rel_path,
        'category': rel_path.split('/')[0],
        'colors': [c1, c2],
    }
    built_count += 1

# Write icons.json
manifest_path = os.path.join(output_dir, 'icons.json')
with open(manifest_path, 'w', encoding='utf-8') as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

# Write README.md documentation per icon-system skill
readme_path = os.path.join(output_dir, 'README.md')
readme_content = """# Remnabot Icon System (Remix Icon Standard)

Single Source of Truth (SSOT) for all vector iconography in Remnabot WebApp and Admin interfaces.
Powered by **Remix Icon 4.9.1**.

## 1. Foundations & Grid Spec
- **Grid Box**: Standard `24x24 px` (`viewBox="0 0 24 24"`)
- **Visual Weight**: Filled variants (`-fill`) for primary state and high-contrast recognition; line variants (`-line`) for secondary toggles/actions.
- **Rendering**: Self-contained SVG assets with WCAG-AA compliant gradients designed for dark (`#0f172a`) and light (`#ffffff`) surfaces.

## 2. Strict Typography-to-Icon Size Pairing

| Component / Typography | Icon Class | Icon Pixels | Usage Context |
| :--- | :--- | :--- | :--- |
| **Micro Badges (`text-[10px]` - `text-[11px]`)** | `w-3.5 h-3.5` | `14x14 px` | Status tags, discount badges, loyalty chips |
| **Button / List Items (`text-xs` / 12px)** | `w-4 h-4` | `16x16 px` | Standard buttons, quick actions, form controls |
| **Card / Subheadings (`text-sm` / 14px)** | `w-4.5 h-4.5` / `w-5 h-5` | `18-20 px` | Section titles, card header bars |
| **Modal / Section Headers (`text-base` / 16px)** | `w-5 h-5` | `20x20 px` | Dialog headers, action sheet titles |
| **Bottom Navigation Bar (`text-[11px]`)** | `w-6 h-6` | `24x24 px` | 5 main mobile tabs inside `44x30 px` pill |
| **Hero Illustrations (`text-xl`+)** | `w-8 h-8` | `32x32 px` | Empty states, success celebration screens |

## 3. Maintenance & Rebuild
To regenerate all Remix Icon SVGs from `node_modules/remixicon/icons/`:
```bash
python scripts/build_remix_icons.py
```
"""

with open(readme_path, 'w', encoding='utf-8') as f:
    f.write(readme_content)

print(f"Successfully generated {built_count} Remix Icon SVGs, icons.json, and README.md!")
