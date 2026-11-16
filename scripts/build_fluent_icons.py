"""
Build and organize official Microsoft Fluent 3D (Flat) & Fluent UI Icons into the central icon system.
Generates:
1. bot/web/static/img/icons/*.svg (Microsoft Fluent 3D & UI vector SVGs)
2. bot/web/static/img/icons/icons.json (Registry of icons, categories, and Fluent origins)
3. bot/web/static/img/icons/README.md (Icon System Specification based on Microsoft Fluent Standard)
"""

import os
import re
import json

output_dir = os.path.join('bot', 'web', 'static', 'img', 'icons')
os.makedirs(output_dir, exist_ok=True)

# Load Fluent Emoji Flat collection
emoji_coll_path = os.path.join('scratch', 'fluent_emoji_flat_collection.json')
with open(emoji_coll_path, 'r', encoding='utf-8') as f:
    emoji_icons = json.load(f)['icons']

# Load Functional Fluent icons
func_path = os.path.join('scratch', 'fluent_functional_icons.json')
with open(func_path, 'r', encoding='utf-8') as f:
    func_icons = json.load(f)

# Fluent 3D Flat Emoji Mappings
FLUENT_3D_EMOJI_MAP = {
    # 1. Navigation & Core Sections
    'dashboard': ('bar-chart', 'Navigation'),
    'reports': ('page-with-curl', 'Navigation'),
    'shop': ('shopping-cart', 'Navigation'),
    'wallet': ('purse', 'Navigation'),
    'profile': ('bust-in-silhouette', 'Navigation'),
    'settings': ('gear', 'System'),
    'users': ('busts-in-silhouette', 'System'),
    'nodes': ('control-knobs', 'System'),
    'finance': ('money-bag', 'Finance'),
    'plans': ('package', 'Commerce'),
    'package': ('package', 'Commerce'),
    
    # 2. Status, Actions & Badges
    'zap': ('high-voltage', 'Status'),
    'lightning': ('high-voltage', 'Status'),
    'shield': ('shield', 'Security'),
    'lock-shield': ('locked', 'Security'),
    'lock_shield': ('locked', 'Security'),
    'rocket': ('rocket', 'Actions'),
    'gift': ('wrapped-gift', 'Marketing'),
    'cart': ('shopping-cart', 'Commerce'),
    'trophy': ('trophy', 'Gamification'),
    'award': ('military-medal', 'Gamification'),
    'crown': ('crown', 'Gamification'),
    'diamond': ('gem-stone', 'Gamification'),
    'star': ('star', 'Gamification'),
    'sparkles': ('sparkle', 'Gamification'),
    'flame': ('fire', 'Status'),
    'clock': ('alarm-clock', 'Time'),
    'calendar': ('tear-off-calendar', 'Time'),
    'check': ('check-mark-button', 'Status'),
    'cross': ('cross-mark', 'Status'),
    'warning': ('warning', 'Status'),
    'ban': ('prohibited', 'Status'),
    'trash': ('wastebasket', 'Actions'),
    'edit': ('pencil', 'Actions'),
    'globe': ('globe-with-meridians', 'Network'),
    'link': ('link', 'Network'),
    'key': ('key', 'Security'),
    'phone': ('mobile-phone', 'Device'),
    'desktop': ('desktop-computer', 'Device'),
    'antenna': ('satellite-antenna', 'Network'),
    'signal': ('antenna-bars', 'Network'),
    'chat': ('speech-balloon', 'Communication'),
    'support': ('headphone', 'Communication'),
    'ticket': ('ticket', 'Marketing'),
    'cake': ('birthday-cake', 'Marketing'),
    'receipt': ('receipt', 'Finance'),
    'coins': ('coin', 'Finance'),
    'credit-card': ('credit-card', 'Finance'),
    'credit_card': ('credit-card', 'Finance'),
    'sun': ('sun', 'Theme'),
    'moon': ('crescent-moon', 'Theme'),
    'sunrise': ('sunrise', 'Theme'),
    'sunset': ('sunset', 'Theme'),
    'sync': ('counterclockwise-arrows-button', 'Actions'),
    'inbox': ('inbox-tray', 'System'),
    'database': ('card-file-box', 'System'),
    'wheel': ('slot-machine', 'Gamification'),
    'gamepad': ('video-game', 'Gamification'),
    'layers': ('card-index-dividers', 'System'),
    'route': ('compass', 'Navigation'),
    'recycle': ('recycling-symbol', 'System'),
    'lightbulb': ('light-bulb', 'Tips'),
    'pie-chart': ('chart-increasing', 'Reports'),
    'bell': ('bell', 'Notifications'),
    'tutorial': ('open-book', 'Help'),
    'faq': ('red-question-mark', 'Help'),
    
    # 3. Medals
    'medal-gold': ('1st-place-medal', 'Loyalty'),
    'medal_gold': ('1st-place-medal', 'Loyalty'),
    'medal-silver': ('2nd-place-medal', 'Loyalty'),
    'medal_silver': ('2nd-place-medal', 'Loyalty'),
    'medal-bronze': ('3rd-place-medal', 'Loyalty'),
    'medal_bronze': ('3rd-place-medal', 'Loyalty'),
}

# Official Brand Logos (preserve intact)
BRAND_LOGOS = {'android', 'ios', 'windows', 'macos', 'linux', 'ton', 'tron', 'polygon'}

manifest = {}
built_count = 0

# 1. Generate Fluent 3D Emoji Icons
for name, (icon_key, category) in FLUENT_3D_EMOJI_MAP.items():
    if icon_key not in emoji_icons:
        print(f"ERROR: missing emoji {icon_key} for {name}")
        continue
    body = emoji_icons[icon_key]['body']
    svg_content = f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">{body}</svg>'
    
    out_file = os.path.join(output_dir, f"{name}.svg")
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(svg_content)
    
    manifest[name] = {
        'source': f'fluent-emoji-flat:{icon_key}',
        'category': category,
        'style': 'fluent-3d-flat'
    }
    built_count += 1

# 2. Generate Functional Fluent UI Icons
for name, raw_svg in func_icons.items():
    # Clean up attributes
    s = re.sub(r'\s+width="[^"]+"', '', raw_svg)
    s = re.sub(r'\s+height="[^"]+"', '', s)
    # Ensure viewBox and width/height 24x24
    if 'viewBox' not in s:
        s = s.replace('<svg ', '<svg viewBox="0 0 24 24" ', 1)
    s = s.replace('<svg ', '<svg width="24" height="24" ', 1)
    
    out_file = os.path.join(output_dir, f"{name}.svg")
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(s)
    
    manifest[name] = {
        'source': f'fluent:{name}',
        'category': 'Controls',
        'style': 'fluent-ui-filled'
    }
    built_count += 1

# 3. Add Brand logos to manifest
for brand in BRAND_LOGOS:
    manifest[brand] = {
        'source': f'official-brand:{brand}',
        'category': 'Logos',
        'style': 'official-vector'
    }

# Write icons.json
manifest_path = os.path.join(output_dir, 'icons.json')
with open(manifest_path, 'w', encoding='utf-8') as f:
    json.dump(manifest, f, indent=2, ensure_ascii=False)

# Write README.md documentation
readme_path = os.path.join(output_dir, 'README.md')
readme_content = """# Remnabot Icon System (Microsoft Fluent 3D Standard)

Single Source of Truth (SSOT) for all vector iconography in Remnabot WebApp and Admin interfaces.
Powered by **Microsoft Fluent 3D (Flat Vector)** and **Microsoft Fluent System UI**.

## 1. Foundations & Grid Spec
- **Fluent 3D Icons**: `32x32 px` (`viewBox="0 0 32 32"`) with rich, vibrant multi-tone 3D depth and shadows.
- **Fluent UI Controls**: `24x24 px` (`viewBox="0 0 24 24"`) filled vector paths with `currentColor` / system tokens.
- **Rendering**: Self-contained SVG assets with WCAG-AA compliant contrasts designed for dark (`#0f172a`) and light surfaces.

## 2. Typography-to-Icon Size Pairing

| Component / Typography | Icon Class | Usage Context |
| :--- | :--- | :--- |
| **Micro Badges (`text-[10px]` - `text-[11px]`)** | `w-3.5 h-3.5` | Status tags, discount badges, loyalty chips |
| **Button / List Items (`text-xs` / 12px)** | `w-4 h-4` | Standard buttons, quick actions, form controls |
| **Card / Subheadings (`text-sm` / 14px)** | `w-4.5 h-4.5` / `w-5 h-5` | Section titles, card header bars |
| **Modal / Section Headers (`text-base` / 16px)** | `w-5 h-5` | Dialog headers, action sheet titles |
| **Bottom Navigation Bar (`text-[11px]`)** | `w-6 h-6` | 5 main mobile tabs inside `.nav-icon-pill` |
| **Hero Illustrations (`text-xl`+)** | `w-8 h-8` | Empty states, success celebration screens |

## 3. Maintenance & Rebuild
To regenerate all Microsoft Fluent SVGs:
```bash
python scripts/build_fluent_icons.py
```
"""

with open(readme_path, 'w', encoding='utf-8') as f:
    f.write(readme_content)

print(f"Successfully generated {built_count} Microsoft Fluent Icon SVGs, icons.json, and README.md!")
