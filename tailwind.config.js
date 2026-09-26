/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./content/**/*.{html,md}",
    "./layouts/**/*.{html,md}",
    "./themes/my-basketball-theme/layouts/**/*.{html,md}",
    "./static/**/*.js"
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: '#f0f7ff',
          100: '#e0effe',
          500: '#0284c7',
          600: '#0369a1',
          700: '#075985',
          800: '#0c4a6e',
          900: '#0f172a',
        },
        accent: {
          500: '#f97316',
          600: '#ea580c',
        }
      }
    },
  },
  plugins: [],
}
