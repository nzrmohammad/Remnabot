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
