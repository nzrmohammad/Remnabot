/**
 * Remnabot Centralized Icon System (Remix Icon Standard)
 * Single Source of Truth for frontend iconography, sizing scales, and cache busting.
 */
(function() {
  'use strict';

  const ICON_VERSION = 'ri4';
  const ICON_BASE_PATH = '/static/img/icons';

  // Standardized typography-to-icon sizing scale
  const SIZE_SCALE = {
    xs: 'w-3.5 h-3.5', // 14px - For micro badges, pills, 10-11px text
    sm: 'w-4 h-4',     // 16px - For buttons, form items, 12px text
    md: 'w-5 h-5',     // 20px - For card titles, subheaders, 14-16px text
    lg: 'w-6 h-6',     // 24px - For bottom nav tabs, key cards
    xl: 'w-8 h-8',     // 32px - For hero illustrations, empty states
  };

  /**
   * Render an optimized Remix Icon img tag with automatic cache-busting.
   * @param {string} name - The semantic icon identifier (e.g. 'dashboard', 'wallet', 'shop')
   * @param {string} sizeOrClass - Preset ('xs', 'sm', 'md', 'lg', 'xl') or arbitrary Tailwind classes
   * @param {Object} [options] - Additional attributes
   * @returns {string} HTML string
   */
  function renderIcon(name, sizeOrClass = 'sm', options = {}) {
    const cleanName = String(name || 'sparkles').trim().toLowerCase().replace('.svg', '');
    const sizeClass = SIZE_SCALE[sizeOrClass] || sizeOrClass || SIZE_SCALE.sm;
    const extraClass = options.class || '';
    const alt = options.alt || '';
    const loading = options.loading || 'eager';
    const ariaHidden = options.ariaHidden !== false ? 'true' : 'false';

    const src = `${ICON_BASE_PATH}/${cleanName}.svg?v=${ICON_VERSION}`;
    return `<img src="${src}" class="ui-icon ui-icon-img shrink-0 ${sizeClass} ${extraClass}".trim() alt="${alt}" aria-hidden="${ariaHidden}" loading="${loading}" />`;
  }

  // Export to window
  window.IconSystem = {
    version: ICON_VERSION,
    basePath: ICON_BASE_PATH,
    sizes: SIZE_SCALE,
    render: renderIcon,
  };

  // Re-link window.uiIcon to point to the centralized system
  window.uiIcon = function(name, sizeOrClass = 'w-4 h-4') {
    return renderIcon(name, sizeOrClass);
  };
})();
