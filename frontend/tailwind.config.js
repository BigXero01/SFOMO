/** @type {import('tailwindcss').Config} */
module.exports = {
  content: [
    "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
    "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          DEFAULT: "#00d4ff",
          dark: "#0099bb",
        },
        surface: {
          DEFAULT: "#0f1117",
          card: "#1a1d27",
          border: "#2a2d3e",
        },
        success: "#00e676",
        danger: "#ff4444",
        warning: "#ffab00",
      },
      fontFamily: {
        mono: ["JetBrains Mono", "Fira Code", "monospace"],
      },
    },
  },
  plugins: [],
};
