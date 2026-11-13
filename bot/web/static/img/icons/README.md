# Remnabot Icon System (Remix Icon Standard)

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
