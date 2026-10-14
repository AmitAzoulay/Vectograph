/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    extend: {
      colors: {
        // Neutral palette tuned for a "premium security product" dark UI.
        ink: {
          950: '#05070d',
          900: '#0a0f1a',
          800: '#0f172a',
          700: '#1e293b',
          600: '#334155',
        },
        accent: {
          DEFAULT: '#22d3ee',
          soft: '#0e7490',
        },
      },
      fontFamily: {
        sans: ['Inter', 'system-ui', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'monospace'],
      },
      boxShadow: {
        glow: '0 0 0 1px rgba(8,145,178,0.35), 0 0 24px -6px rgba(8,145,178,0.35)',
        panel: '0 20px 45px -28px rgba(15,23,42,0.35)',
      },
      keyframes: {
        'fade-in': {
          '0%': { opacity: 0, transform: 'translateY(8px)' },
          '100%': { opacity: 1, transform: 'translateY(0)' },
        },
        'pulse-ring': {
          '0%': { transform: 'scale(0.9)', opacity: 0.7 },
          '100%': { transform: 'scale(1.6)', opacity: 0 },
        },
        float: {
          '0%,100%': { transform: 'translateY(0)' },
          '50%': { transform: 'translateY(-6px)' },
        },
      },
      animation: {
        'fade-in': 'fade-in 0.35s ease-out both',
        'pulse-ring': 'pulse-ring 1.8s cubic-bezier(0.4,0,0.6,1) infinite',
        float: 'float 4s ease-in-out infinite',
      },
    },
  },
  plugins: [],
}
