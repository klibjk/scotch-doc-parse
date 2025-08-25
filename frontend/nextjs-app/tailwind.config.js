/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/app/**/*.{ts,tsx}",
    "./src/components/**/*.{ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        surface: '#f6f6f6', // slightly off-white
        ink: '#111111',
        outline: '#0d0d0d',
      },
      fontFamily: {
        ui: ["Inter", "system-ui", "sans-serif"],
      },
      borderRadius: {
        xl: '16px',
      }
    },
  },
  plugins: [],
}


