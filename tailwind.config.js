/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: 'class',
  content: [
    "./bot/web/templates/**/*.html",
    "./bot/web/static/js/**/*.js"
  ],
  theme: {
    extend: {
      colors: {
        'slate-750': '#293548',
        surface: {
          DEFAULT: 'var(--card-bg)',
          page: 'var(--page-bg)',
          frame: 'var(--frame-bg)',
          inner: 'var(--card-inner-bg)',
          modal: 'var(--modal-bg)',
        },
        border: {
          DEFAULT: 'var(--card-border)',
          frame: 'var(--frame-border)',
          modal: 'var(--modal-border)',
        },
        content: {
          DEFAULT: 'var(--text-main)',
          main: 'var(--text-main)',
          muted: 'var(--text-muted)',
          subtle: 'var(--text-subtle)',
          inverse: 'var(--text-inverse)',
        },
      },
      fontSize: {
        '2xs': ['10px', '14px'],
        'caption': ['11px', '15px'],
      },
      keyframes: {
        fadeIn: {
          '0%': { opacity: '0', transform: 'scale(0.98)' },
          '100%': { opacity: '1', transform: 'scale(1)' },
        },
      },
      animation: {
        fadeIn: 'fadeIn 0.2s ease-out forwards',
      },
    },
  },
  safelist: [
    'text-emerald-400',
    'text-amber-400',
    'text-rose-400',
    'text-cyan-400',
    'text-blue-400',
    'text-slate-400',
    'border-emerald-500',
    'border-cyan-500',
    'border-rose-500',
    'border-emerald-400',
    'border-cyan-400',
    'border-rose-400',
    'bg-emerald-500/10',
    'bg-cyan-500/10',
    'bg-rose-500/10',
  ],
  plugins: [],
}
