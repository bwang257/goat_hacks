/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        mbta: {
          blue: '#003882',
          red: '#DA291C',
          orange: '#ED8B00',
          green: '#00843D',
        },
      },
    },
  },
  plugins: [],
}

