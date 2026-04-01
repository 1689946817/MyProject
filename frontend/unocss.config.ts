import { defineConfig, presetUno, presetIcons } from 'unocss'

export default defineConfig({
  presets: [
    presetUno(),
    presetIcons({
      scale: 1.2,
      cdn: 'https://esm.sh/'
    })
  ],
  theme: {
    colors: {
      dark: {
        primary: '#0f0f1a',
        secondary: '#1a1a2e',
        tertiary: '#252540',
      },
      accent: {
        primary: '#00d4ff',
        secondary: '#7c3aed',
      }
    }
  },
  shortcuts: {
    'flex-center': 'flex justify-center items-center',
    'flex-between': 'flex justify-between items-center',
    'neon-border': 'border border-[#00d4ff]/30 hover:border-[#00d4ff]/60 transition-all duration-300',
    'glass-card': 'bg-[#1a1a2e]/80 backdrop-blur-sm rounded-lg',
  }
})
