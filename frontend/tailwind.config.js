/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      fontFamily: {
        display: ['"DM Serif Display"', 'Georgia', 'serif'],
        mono:    ['"JetBrains Mono"', '"Fira Code"', 'monospace'],
        sans:    ['"DM Sans"', 'system-ui', 'sans-serif'],
      },
      colors: {
        ink:    '#0f1117',
        slate:  '#1e2230',
        panel:  '#252a38',
        border: '#2e3447',
        muted:  '#4a5168',
        ghost:  '#6b7494',
        silver: '#9ba3bf',
        cloud:  '#c8cfe0',
        snow:   '#f0f2f8',
        // Accent palette
        azure:  '#3b82f6',
        teal:   '#14b8a6',
        amber:  '#f59e0b',
        rose:   '#f43f5e',
        violet: '#8b5cf6',
        sage:   '#10b981',
      },
      boxShadow: {
        card:  '0 1px 3px rgba(0,0,0,0.4), 0 0 0 1px rgba(255,255,255,0.04)',
        glow:  '0 0 20px rgba(59,130,246,0.15)',
        inset: 'inset 0 1px 0 rgba(255,255,255,0.06)',
      },
      keyframes: {
        'fade-up': {
          '0%':   { opacity: '0', transform: 'translateY(12px)' },
          '100%': { opacity: '1', transform: 'translateY(0)' },
        },
        'count-up': {
          '0%':   { opacity: '0' },
          '100%': { opacity: '1' },
        },
        shimmer: {
          '0%':   { backgroundPosition: '-200% 0' },
          '100%': { backgroundPosition: '200% 0' },
        },
      },
      animation: {
        'fade-up':  'fade-up 0.4s ease both',
        'count-up': 'count-up 0.6s ease both',
        shimmer:    'shimmer 1.5s infinite linear',
      },
    },
  },
  plugins: [],
}
