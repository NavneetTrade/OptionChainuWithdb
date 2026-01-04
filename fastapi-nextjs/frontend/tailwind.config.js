/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    './pages/**/*.{js,ts,jsx,tsx,mdx}',
    './components/**/*.{js,ts,jsx,tsx,mdx}',
    './app/**/*.{js,ts,jsx,tsx,mdx}',
  ],
  theme: {
    extend: {
      colors: {
        'gamma-red': '#FF5555',
        'gamma-green': '#00E676',
        'gamma-blue': '#448AFF',
        'dark-bg': '#0E1117',
        'dark-card': '#1E1E2E',
      },
    },
  },
  plugins: [],
}
