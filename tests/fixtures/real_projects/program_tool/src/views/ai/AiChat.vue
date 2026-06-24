<template>
  <ToolPanel title="AI chat" description="Chat conversation with markdown history export and highlighted code">
    <section class="ai-chat-container">
      <div class="chat-messages">
        <article v-for="message in messages" :key="message.id" v-html="formatMessageContent(message.content)" />
      </div>
      <textarea v-model="input" placeholder="Ask the assistant"></textarea>
      <button @click="sendMessage">send chat message</button>
      <button @click="exportChat">export conversation history</button>
    </section>
  </ToolPanel>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import ToolPanel from '@/components/ToolPanel.vue'
import { safeRenderMarkdown, setupCodeCopyFunction } from '@/utils/markdownUtils'

interface ChatMessage {
  id: string
  role: 'user' | 'assistant'
  content: string
}

const input = ref('')
const messages = ref<ChatMessage[]>([])

setupCodeCopyFunction()

async function sendMessage() {
  const userMessage: ChatMessage = {
    id: `message-${Date.now()}`,
    role: 'user',
    content: input.value,
  }
  messages.value.push(userMessage)
  messages.value.push({
    id: `assistant-${Date.now()}`,
    role: 'assistant',
    content: '```ts\nconst highlighted = true\n```',
  })
}

function formatMessageContent(content: string): string {
  return safeRenderMarkdown(content)
}

function exportChat(): string {
  return JSON.stringify({ conversation: messages.value, exportedAt: new Date().toISOString() })
}
</script>
