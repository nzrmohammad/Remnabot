# Remnabot Icon System (Microsoft Fluent 3D Standard)

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
