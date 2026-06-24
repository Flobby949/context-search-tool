import type { WatermarkRegion } from '@/types'

export function loadImage(file: File | Blob): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const image = new Image()
    const url = URL.createObjectURL(file)
    image.onload = () => {
      URL.revokeObjectURL(url)
      resolve(image)
    }
    image.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error('image load failed'))
    }
    image.src = url
  })
}

export function eraseArea(canvas: HTMLCanvasElement, region: WatermarkRegion): void {
  const context = canvas.getContext('2d')
  if (!context) return

  const imageData = context.getImageData(0, 0, canvas.width, canvas.height)
  const fill = averageEdgeColor(imageData, region)
  context.fillStyle = `rgb(${fill.r}, ${fill.g}, ${fill.b})`
  context.fillRect(region.x, region.y, region.width, region.height)
}

export function createMaskCanvas(
  width: number,
  height: number,
  regions: WatermarkRegion[],
): HTMLCanvasElement {
  const mask = document.createElement('canvas')
  mask.width = width
  mask.height = height
  const context = mask.getContext('2d')
  if (!context) return mask

  context.fillStyle = 'black'
  for (const region of regions) {
    context.fillRect(region.x, region.y, region.width, region.height)
  }
  return mask
}

export function inpaintMaskedArea(
  canvas: HTMLCanvasElement,
  mask: HTMLCanvasElement,
): HTMLCanvasElement {
  const context = canvas.getContext('2d')
  const maskContext = mask.getContext('2d')
  if (!context || !maskContext) return canvas

  const maskData = maskContext.getImageData(0, 0, mask.width, mask.height)
  for (let index = 3; index < maskData.data.length; index += 4) {
    if (maskData.data[index] > 0) {
      const pixel = (index - 3) / 4
      const x = pixel % mask.width
      const y = Math.floor(pixel / mask.width)
      context.clearRect(x, y, 1, 1)
    }
  }
  return canvas
}

export function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}

function averageEdgeColor(
  imageData: ImageData,
  region: WatermarkRegion,
): { r: number; g: number; b: number } {
  const x = Math.max(0, region.x - 1)
  const y = Math.max(0, region.y - 1)
  const index = (y * imageData.width + x) * 4
  return {
    r: imageData.data[index] ?? 255,
    g: imageData.data[index + 1] ?? 255,
    b: imageData.data[index + 2] ?? 255,
  }
}
