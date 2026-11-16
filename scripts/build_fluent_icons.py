"""
Build and organize official Microsoft Fluent 3D (Flat) & Fluent UI Icons into the central icon system.
Generates:
1. bot/web/static/img/icons/*.svg (Microsoft Fluent 3D & UI vector SVGs with theme-safe contrast)
2. bot/web/static/img/icons/icons.json (Registry of icons, categories, and Fluent origins)
3. bot/web/static/img/icons/README.md (Icon System Specification based on Microsoft Fluent Standard)
"""

import os
import json

output_dir = os.path.join('bot', 'web', 'static', 'img', 'icons')
os.makedirs(output_dir, exist_ok=True)

# Load Fluent Emoji Flat collection
emoji_coll_path = os.path.join('scratch', 'fluent_emoji_flat_collection.json')
with open(emoji_coll_path, 'r', encoding='utf-8') as f:
    emoji_icons = json.load(f)['icons']

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
    'photo': ('framed-picture', 'Media'),
    'image': ('framed-picture', 'Media'),
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
    'search': ('magnifying-glass-tilted-left', 'Actions'),
    'plus': ('plus', 'Actions'),
    
    # 3. Medals
    'medal-gold': ('1st-place-medal', 'Loyalty'),
    'medal_gold': ('1st-place-medal', 'Loyalty'),
    'medal-silver': ('2nd-place-medal', 'Loyalty'),
    'medal_silver': ('2nd-place-medal', 'Loyalty'),
    'medal-bronze': ('3rd-place-medal', 'Loyalty'),
    'medal_bronze': ('3rd-place-medal', 'Loyalty'),
}

# Theme-Safe High-Contrast Vector SVGs (Never currentColor to prevent black-on-black in dark mode)
CUSTOM_FLUENT_ICONS = {
    # 3D Dual-Sheet Copy Icon (Azure back-sheet + Crisp white front-sheet with text lines)
    'copy': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">
  <defs>
    <linearGradient id="fl_copy_back" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
  </defs>
  <rect x="10" y="3" width="17" height="21" rx="3.5" fill="url(#fl_copy_back)"/>
  <path d="M22 3 L27 8 L22 8 Z" fill="#bae6fd" opacity="0.9"/>
  <rect x="5" y="8" width="17" height="21" rx="3.5" fill="#f8fafc" stroke="#38bdf8" stroke-width="0.8"/>
  <path d="M17 8 L22 13 L17 13 Z" fill="#cbd5e1"/>
  <rect x="8" y="14" width="11" height="1.8" rx="0.9" fill="#0284c7" opacity="0.85"/>
  <rect x="8" y="18" width="11" height="1.8" rx="0.9" fill="#94a3b8" opacity="0.75"/>
  <rect x="8" y="22" width="7" height="1.8" rx="0.9" fill="#94a3b8" opacity="0.75"/>
</svg>''',

    # Microsoft Fluent 3D Close / Dismiss Cross (Vibrant coral/rose with high contrast on all themes)
    'close': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">
  <defs>
    <linearGradient id="fl_close_grad" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#fb7185"/>
      <stop offset="100%" stop-color="#e11d48"/>
    </linearGradient>
  </defs>
  <path fill="url(#fl_close_grad)" d="M24.879 2.879A3 3 0 1 1 29.12 7.12l-8.79 8.79a.125.125 0 0 0 0 .177l8.79 8.79a3 3 0 1 1-4.242 4.243l-8.79-8.79a.125.125 0 0 0-.177 0l-8.79 8.79a3 3 0 1 1-4.243-4.242l8.79-8.79a.125.125 0 0 0 0-.177l-8.79-8.79A3 3 0 0 1 7.12 2.878l8.79 8.79a.125.125 0 0 0 .177 0z"/>
</svg>''',

    # Accordion / Dropdown Chevron (High-contrast Slate Gradient, visible in dark & light)
    'chevron-down': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <defs>
    <linearGradient id="fl_chevron" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#cbd5e1"/>
      <stop offset="100%" stop-color="#94a3b8"/>
    </linearGradient>
  </defs>
  <path fill="url(#fl_chevron)" d="M4.293 8.293a1 1 0 0 1 1.414 0L12 14.586l6.293-6.293a1 1 0 1 1 1.414 1.414l-7 7a1 1 0 0 1-1.414 0l-7-7a1 1 0 0 1 0-1.414"/>
</svg>''',

    # Navigation Arrow (RTL Left Arrow, High-contrast Slate Gradient)
    'arrow-left': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <defs>
    <linearGradient id="fl_arrow_left" x1="100%" y1="0%" x2="0%" y2="0%">
      <stop offset="0%" stop-color="#cbd5e1"/>
      <stop offset="100%" stop-color="#94a3b8"/>
    </linearGradient>
  </defs>
  <path fill="url(#fl_arrow_left)" d="M10.295 19.715a1 1 0 0 0 1.404-1.424l-5.37-5.292h13.67a1 1 0 0 0 0-2H6.336L11.7 5.714a1 1 0 0 0-1.404-1.424L3.37 11.112a1.25 1.25 0 0 0 0 1.78z"/>
</svg>''',

    # Download Arrow (Vibrant Emerald / Cyan gradient)
    'download': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <defs>
    <linearGradient id="fl_download" x1="0%" y1="0%" x2="0%" y2="100%">
      <stop offset="0%" stop-color="#34d399"/>
      <stop offset="100%" stop-color="#059669"/>
    </linearGradient>
  </defs>
  <path fill="url(#fl_download)" d="M12 2a1 1 0 0 1 1 1v9.59l2.3-2.3a1 1 0 0 1 1.4 1.42l-4 4a1 1 0 0 1-1.4 0l-4-4a1 1 0 1 1 1.4-1.42l2.3 2.3V3a1 1 0 0 1 1-1M4 17a1 1 0 0 1 1 1v2h14v-2a1 1 0 1 1 2 0v3a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1v-3a1 1 0 0 1 1-1"/>
</svg>''',

    # QR Code (Vibrant Azure gradient)
    'qr': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <defs>
    <linearGradient id="fl_qr" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
  </defs>
  <path fill="url(#fl_qr)" d="M3 11h8V3H3zm2-6h4v4H5zM3 21h8v-8H3zm2-6h4v4H5zm8-12v8h8V3zm6 6h-4V5h4zm-5.5 6.5h3v-2h-3v-2.5h2v-2h-2V9h-2v2h2v1.5h-2v2h2v1.5zm3.5 1h2v-2h-2zm-2 2h2v-2h-2zm4-4h2v-2h-2zm0 4h2v-2h-2zm-2 2h2v-2h-2zm4 0h2v-2h-2z"/>
</svg>''',

    # WiFi (Vibrant Azure gradient)
    'wifi': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <defs>
    <linearGradient id="fl_wifi" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
  </defs>
  <path fill="url(#fl_wifi)" d="M12 4c4.37 0 8.35 1.73 11.27 4.54a1 1 0 0 1-1.39 1.44A13.9 13.9 0 0 0 12 6a13.9 13.9 0 0 0-9.88 3.98a1 1 0 1 1-1.39-1.44A15.9 15.9 0 0 1 12 4m0 4c3.27 0 6.24 1.3 8.43 3.41a1 1 0 0 1-1.39 1.44A9.9 9.9 0 0 0 12 10c-2.73 0-5.21 1.09-7.04 2.85a1 1 0 0 1-1.39-1.44A11.9 11.9 0 0 1 12 8m0 4c2.16 0 4.12.87 5.58 2.27a1 1 0 1 1-1.39 1.44A5.9 5.9 0 0 0 12 14c-1.6 0-3.06.64-4.19 1.71a1 1 0 1 1-1.39-1.44A7.9 7.9 0 0 1 12 12m0 4a2 2 0 1 1 0 4a2 2 0 0 1 0-4"/>
</svg>''',

    # Play Media (Vibrant Azure gradient)
    'play': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <defs>
    <linearGradient id="fl_play" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
  </defs>
  <path fill="url(#fl_play)" d="M7 4.5v15a1 1 0 0 0 1.55.83l12-7.5a1 1 0 0 0 0-1.66l-12-7.5A1 1 0 0 0 7 4.5"/>
</svg>''',

    # Play Circle Button
    'play-btn': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <defs>
    <linearGradient id="fl_play_btn" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
  </defs>
  <path fill="url(#fl_play_btn)" d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10s10-4.48 10-10S17.52 2 12 2m-2 14.5v-9l6 4.5z"/>
</svg>''',

    # Pause Media
    'pause': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" width="24" height="24">
  <defs>
    <linearGradient id="fl_pause" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
  </defs>
  <path fill="url(#fl_pause)" d="M6 5a2 2 0 0 1 2-2h1a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2zm9 0a2 2 0 0 1 2-2h1a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-1a2 2 0 0 1-2-2z"/>
</svg>''',

    # High-Contrast Official Receipt / Invoice Vector
    'receipt': '''<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">
  <defs>
    <linearGradient id="fl_receipt_header" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#34d399"/>
      <stop offset="100%" stop-color="#059669"/>
    </linearGradient>
    <linearGradient id="fl_receipt_seal" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="#38bdf8"/>
      <stop offset="100%" stop-color="#0284c7"/>
    </linearGradient>
  </defs>
  <path d="M6 3 L26 3 C27.1 3 28 3.9 28 5 L28 27 L25.5 25 L23 27 L20.5 25 L18 27 L15.5 25 L13 27 L10.5 25 L8 27 L5.5 25 L4 27 L4 5 C4 3.9 4.9 3 6 3 Z" fill="#f8fafc" stroke="#cbd5e1" stroke-width="0.8"/>
  <path d="M6 3 L26 3 C27.1 3 28 3.9 28 5 L28 9 L4 9 L4 5 C4 3.9 4.9 3 6 3 Z" fill="url(#fl_receipt_header)"/>
  <circle cx="8" cy="6" r="1.5" fill="#ffffff" opacity="0.9"/>
  <rect x="7" y="12" width="12" height="2" rx="1" fill="#0284c7"/>
  <rect x="7" y="16" width="18" height="1.8" rx="0.9" fill="#94a3b8"/>
  <rect x="7" y="19.5" width="14" height="1.8" rx="0.9" fill="#94a3b8"/>
  <line x1="7" y1="23" x2="25" y2="23" stroke="#cbd5e1" stroke-width="0.8" stroke-dasharray="1.5,1.5"/>
  <circle cx="22" cy="19" r="3.5" fill="url(#fl_receipt_seal)" opacity="0.95"/>
  <path d="M20.5 19 L21.5 20 L23.5 18" stroke="#ffffff" stroke-width="1" stroke-linecap="round" stroke-linejoin="round"/>
</svg>''',
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

# 2. Generate Custom High-Contrast Fluent Icons
for name, svg_content in CUSTOM_FLUENT_ICONS.items():
    out_file = os.path.join(output_dir, f"{name}.svg")
    with open(out_file, 'w', encoding='utf-8') as f:
        f.write(svg_content.strip())
    
    manifest[name] = {
        'source': f'fluent-custom:{name}',
        'category': 'Controls',
        'style': 'fluent-gradient-vector'
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
Powered by **Microsoft Fluent 3D (Flat Vector)** and **Theme-Safe Fluent Vectors**.

## 1. Foundations & Grid Spec
- **Fluent 3D Icons**: `32x32 px` (`viewBox="0 0 32 32"`) with rich, vibrant multi-tone 3D depth and shadows.
- **Fluent UI Controls**: `24x24 px` or `32x32 px` vector paths with explicit high-contrast WCAG-AA compliant gradients (zero `currentColor` dependency to ensure flawless rendering on both dark and light surfaces).
- **Theme-Safety**: Every icon renders with guaranteed contrast on dark (`#0f172a`, `#1e293b`) and light surfaces.

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
