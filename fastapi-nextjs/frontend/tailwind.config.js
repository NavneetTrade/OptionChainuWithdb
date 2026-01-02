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
        'gamma-red': '#FF4B4B',
        'gamma-green': '#00C853',
        'gamma-blue': '#2962FF',
        'dark-bg': '#0E1117',
        'dark-card': '#262730',
      },
    },
  },
  plugins: [],
}
