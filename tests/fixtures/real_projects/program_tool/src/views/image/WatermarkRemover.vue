<template>
  <ToolPanel title="Watermark remover" description="Detect and remove image watermarks">
    <button @click="detectWatermarks">detect watermark regions</button>
    <button @click="processWatermarks">remove watermark mask with canvas inpaint</button>
    <canvas ref="previewCanvas"></canvas>
  </ToolPanel>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'
import ToolPanel from '@/components/ToolPanel.vue'
import type { DetectionConfig, WatermarkRegion } from '@/types'
import { DEFAULT_DETECTION_CONFIG, FrontendDetector } from '@/services/watermarkDetection'
import { eraseArea, loadImage } from '@/utils/imageUtils'

const detectionConfig = reactive<DetectionConfig>({ ...DEFAULT_DETECTION_CONFIG })
const detectedRegions = ref<WatermarkRegion[]>([])
const selectedRegionIds = ref<Set<string>>(new Set())
const previewCanvas = ref<HTMLCanvasElement | null>(null)
const detector = new FrontendDetector()

async function detectWatermarks() {
  const image = await loadImage(new File([], 'sample.png'))
  const canvas = document.createElement('canvas')
  canvas.width = image.width
  canvas.height = image.height
  const ctx = canvas.getContext('2d')
  if (!ctx) return
  ctx.drawImage(image, 0, 0)
  const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height)
  detectedRegions.value = await detector.detect(imageData, detectionConfig)
  selectedRegionIds.value = new Set(detectedRegions.value.map((region) => region.id))
}

function processWatermarks() {
  if (!previewCanvas.value) return
  for (const region of detectedRegions.value) {
    if (selectedRegionIds.value.has(region.id)) {
      eraseArea(previewCanvas.value, region)
    }
  }
}
</script>
