/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ink: {
          DEFAULT: '#111827',
          dark: '#0B0F19',
          light: '#1F2937',
        },
        accent: {
          DEFAULT: '#4338CA',
          hover: '#3730A3',
          light: '#6366F1',
          soft: '#EEF2FF',
          softer: '#F5F7FF',
        },
        surface: {
          50: '#F9FAFB',
          100: '#F3F4F6',
          200: '#E5E7EB',
          300: '#D1D5DB',
        },
        grayText: {
          600: '#6B7280',
          400: '#9CA3AF',
        },
        status: {
          success: '#059669',
          'success-bg': '#ECFDF5',
          'success-border': '#A7F3D0',
          'success-text': '#065F46',
          warning: '#D97706',
          'warning-bg': '#FFFBEB',
          'warning-border': '#FDE68A',
          'warning-text': '#92400E',
          danger: '#DC2626',
          'danger-bg': '#FEF2F2',
          'danger-border': '#FECACA',
          'danger-text': '#991B1B',
        }
      },
      fontFamily: {
        sans: ['"Geist Sans"', 'Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'Roboto', 'sans-serif'],
        mono: ['"Geist Mono"', 'JetBrains Mono', 'ui-monospace', 'SFMono-Regular', 'Menlo', 'Monaco', 'Consolas', 'monospace'],
      },
      boxShadow: {
        'subtle': '0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px 0 rgba(0, 0, 0, 0.03)',
        'card': '0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -1px rgba(0, 0, 0, 0.03)',
        'elevated': '0 10px 25px -5px rgba(0, 0, 0, 0.06), 0 8px 10px -6px rgba(0, 0, 0, 0.03)',
        'floating': '0 20px 25px -5px rgba(17, 24, 39, 0.1), 0 10px 10px -5px rgba(17, 24, 39, 0.04)',
      }
    },
  },
  plugins: [],
}
