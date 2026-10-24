/** @type {import('tailwindcss').Config} */
module.exports = {
  darkMode: ['class'],
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
    './src/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        bg: 'var(--color-bg)',
        surface: {
          DEFAULT: 'var(--color-surface)',
          hover: 'var(--color-surface-hover)',
        },
        border: {
          DEFAULT: 'var(--color-border)',
          input: 'var(--color-border-input)',
        },
        text: {
          DEFAULT: 'var(--color-text)',
          muted: 'var(--color-text-muted)',
        },
        accent: {
          DEFAULT: 'var(--color-accent)',
          foreground: 'var(--color-on-accent)',
        },
        danger: 'var(--color-danger)',
        success: 'var(--color-success)',
        warning: 'var(--color-warning)',
      },
      fontFamily: {
        sans: ['var(--font-sans)'],
        mono: ['var(--font-mono)'],
      },
      fontSize: {
        xs: ['var(--type-xs-size)', { lineHeight: 'var(--type-xs-line)', fontWeight: 'var(--type-xs-weight)' }],
        sm: ['var(--type-sm-size)', { lineHeight: 'var(--type-sm-line)', fontWeight: 'var(--type-sm-weight)' }],
        base: ['var(--type-base-size)', { lineHeight: 'var(--type-base-line)', fontWeight: 'var(--type-base-weight)' }],
        md: ['var(--type-md-size)', { lineHeight: 'var(--type-md-line)', fontWeight: 'var(--type-md-weight)' }],
        lg: ['var(--type-lg-size)', { lineHeight: 'var(--type-lg-line)', fontWeight: 'var(--type-lg-weight)' }],
        xl: ['var(--type-xl-size)', { lineHeight: 'var(--type-xl-line)', fontWeight: 'var(--type-xl-weight)' }],
        '2xl': ['var(--type-2xl-size)', { lineHeight: 'var(--type-2xl-line)', fontWeight: 'var(--type-2xl-weight)' }],
        display: ['var(--type-display-size)', { lineHeight: 'var(--type-display-line)', fontWeight: 'var(--type-display-weight)' }],
      },
      borderRadius: {
        xs: 'var(--radius-xs)',
        sm: 'var(--radius-sm)',
        md: 'var(--radius-md)',
        lg: 'var(--radius-lg)',
        xl: 'var(--radius-xl)',
        pill: 'var(--radius-pill)',
      },
      boxShadow: {
        sm: 'var(--shadow-sm)',
        card: 'var(--shadow-card)',
        pop: 'var(--shadow-pop)',
        glow: 'var(--shadow-glow)',
      },
      transitionTimingFunction: {
        spring: 'cubic-bezier(0.34, 1.56, 0.64, 1)',
      },
      transitionDuration: {
        fast: '150ms',
        base: '250ms',
        slow: '400ms',
      },
    },
  },
  plugins: [],
};
