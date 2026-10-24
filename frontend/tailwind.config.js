/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      fontFamily: {
        sans: ['Nunito', 'system-ui', 'sans-serif'],
      },
      colors: {
        canvas: '#F3F8F4',
        mint: {
          DEFAULT: '#DDF1E4',
          50: '#F3F8F4',
          100: '#DDF1E4',
          200: '#D6F0DF',
          300: '#9FDDB6',
        },
        leaf: '#9FDDB6',
        kidney: {
          DEFAULT: '#22A75A',
          alt: '#34B26B',
          hover: '#1c8c4a',
        },
        forest: {
          DEFAULT: '#17573A',
          hover: '#13472f',
        },
        ink: {
          DEFAULT: '#1B2A22',
          light: '#2A3D33',
          border: '#3A4A41',
        },
        muted: '#5C6E63',
        subtle: '#3E5046',
        cardborder: '#DCE7DF',
        risk: {
          low: { bg: '#D6F0DF', text: '#17573A', dot: '#22A75A' },
          med: { bg: '#FBEBB5', text: '#6B4E00', dot: '#E8B92E' },
          high: { bg: '#F9D3C8', text: '#8A2E1A', dot: '#E57A5F' },
        },
      },
      borderRadius: {
        card: '28px',
        phone: '44px',
        tablet: '40px',
        pill: '999px',
      },
      boxShadow: {
        card: '0 1px 2px rgba(23,87,58,.06), 0 8px 24px rgba(23,87,58,.06)',
        pill: '0 10px 24px rgba(34,167,90,.3)',
        ink: '0 10px 24px rgba(27,42,34,.25)',
      },
    },
  },
  plugins: [],
};
