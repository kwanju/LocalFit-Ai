/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      // C2C/C2S gym screen: the rep number must be readable from a distance.
      fontSize: {
        count: ["12rem", { lineHeight: "1" }],
      },
    },
  },
  plugins: [],
};
