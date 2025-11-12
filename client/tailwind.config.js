/** @type {import('tailwindcss').Config} */
export default {
  content: [
    './index.html',
    './src/**/*.{js,ts,jsx,tsx}'
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          primary: '#8b5cf6',
          secondary: '#7c3aed'
        }
      }
    }
  },
  plugins: []
};
