<template>
  <div class="app-layout" :class="appStore.theme">
    <aside class="sidebar">
      <button class="theme-toggle" @click="appStore.toggleTheme">
        {{ appStore.getThemeDisplayName() }}
      </button>
      <nav>
        <section v-for="category in appStore.toolCategories" :key="category.title">
          <h2>{{ category.title }}</h2>
          <RouterLink v-for="tool in category.tools" :key="tool.path" :to="tool.path">
            {{ tool.name }}
          </RouterLink>
        </section>
      </nav>
    </aside>
    <main>
      <slot />
    </main>
  </div>
</template>

<script setup lang="ts">
import { RouterLink } from 'vue-router'
import { useAppStore } from '@/stores/app'

const appStore = useAppStore()
</script>
