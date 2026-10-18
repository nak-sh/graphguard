import type { Config } from "tailwindcss";

const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        guard: { ink: "#e6edf5", cyan: "#56d6e8", amber: "#f2b45f", red: "#f07878", green: "#73d6a0", violet: "#ae9cff" },
      },
    },
  },
  plugins: [],
};

export default config;
