<template>
  <ToolPanel title="QRCode tool" description="Generate, scan, decode, and paste QR code images">
    <button @click="activeTab = 'generate'">generate QRCode</button>
    <button @click="activeTab = 'parse'">scan camera or decode pasted image</button>
    <textarea v-model="generateOptions.text" placeholder="content to encode"></textarea>
    <button @click="generateQRCode">generate QR code image</button>
    <input type="file" accept="image/*" @change="handleFileSelect" />
    <button @click="parseUploadedQRCode">decode QRCode from file</button>
    <CodeEditor v-model="parseResult" language="text" title="decoded result" />
  </ToolPanel>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import CodeEditor from '@/components/CodeEditor.vue'
import ToolPanel from '@/components/ToolPanel.vue'
import {
  generateQRCode as generateQR,
  isValidColor,
  parseQRCodeFromFile,
  type QRCodeOptions,
} from '@/utils/qrcodeUtils'

const activeTab = ref<'generate' | 'parse'>('generate')
const generatedQRCode = ref('')
const parseResult = ref('')
const selectedFile = ref<File | null>(null)
const generateOptions = reactive<QRCodeOptions>({
  text: 'https://example.com',
  width: 256,
  errorCorrectionLevel: 'M',
  color: { dark: '#000000', light: '#ffffff' },
})

async function generateQRCode() {
  if (!generateOptions.color || !isValidColor(generateOptions.color.dark ?? '')) return
  generatedQRCode.value = await generateQR(generateOptions)
}

function handleFileSelect(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFile.value = input.files?.[0] ?? null
}

async function parseUploadedQRCode() {
  if (!selectedFile.value) return
  parseResult.value = await parseQRCodeFromFile(selectedFile.value)
}
</script>
