import { defineStore } from 'pinia'
import { reactive, ref } from 'vue'
import type { ToolCategory } from '@/types'

export const useAppStore = defineStore('app', () => {
  const currentTool = ref('ai-chat')
  const themePreference = ref<'auto' | 'light' | 'dark'>('auto')
  const theme = ref<'light' | 'dark'>('light')
  const toolCategories = reactive<ToolCategory[]>([
    {
      title: 'Image tools',
      tools: [{ name: 'Watermark remover', path: '/watermark-remover' }],
    },
    {
      title: 'Communication',
      tools: [{ name: 'MQTT test tool', path: '/mqtt-tool' }],
    },
    {
      title: 'JSON tools',
      tools: [{ name: 'JSON to entity', path: '/json-to-entity' }],
    },
    {
      title: 'AI tools',
      tools: [{ name: 'AI chat assistant', path: '/ai-chat' }],
    },
  ])

  function setCurrentTool(tool: string) {
    currentTool.value = tool
  }

  function toggleTheme() {
    theme.value = theme.value === 'dark' ? 'light' : 'dark'
    themePreference.value = theme.value
  }

  function getThemeDisplayName(): string {
    return theme.value === 'dark' ? 'dark mode' : 'light mode'
  }

  return {
    currentTool,
    theme,
    themePreference,
    toolCategories,
    setCurrentTool,
    toggleTheme,
    getThemeDisplayName,
  }
})
