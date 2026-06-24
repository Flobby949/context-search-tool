import type { DetectionConfig, WatermarkRegion } from '@/types'

export const DEFAULT_DETECTION_CONFIG: DetectionConfig = {
  sensitivity: 0.5,
  minRegionSize: 20,
  maxRegionSize: 500,
  confidenceThreshold: 0.3,
}

export class FrontendDetector {
  async detect(imageData: ImageData, config: DetectionConfig): Promise<WatermarkRegion[]> {
    const regions: WatermarkRegion[] = []
    const blockSize = 32

    for (let y = 0; y < imageData.height - blockSize; y += blockSize) {
      for (let x = 0; x < imageData.width - blockSize; x += blockSize) {
        const confidence = this.scoreWatermarkCandidate(imageData, x, y, blockSize, config)
        if (confidence >= config.confidenceThreshold) {
          regions.push({ id: `region-${x}-${y}`, x, y, width: blockSize, height: blockSize, confidence })
        }
      }
    }

    return this.mergeAdjacentRegions(regions, config)
  }

  private scoreWatermarkCandidate(
    imageData: ImageData,
    x: number,
    y: number,
    blockSize: number,
    config: DetectionConfig,
  ): number {
    const edgeDensity = detectEdges(imageData, x, y, blockSize)
    const colorVariance = calculateColorVariance(imageData, x, y, blockSize)
    const maskScore = colorVariance < 2000 ? 0.4 : 0
    const inpaintScore = edgeDensity > 0.15 ? 0.5 : 0.2
    return (maskScore + inpaintScore) * config.sensitivity
  }

  private mergeAdjacentRegions(
    regions: WatermarkRegion[],
    config: DetectionConfig,
  ): WatermarkRegion[] {
    return regions.filter((region) => {
      const area = region.width * region.height
      return area >= config.minRegionSize && area <= config.maxRegionSize * config.maxRegionSize
    })
  }
}

function calculateColorVariance(
  imageData: ImageData,
  startX: number,
  startY: number,
  blockSize: number,
): number {
  return (imageData.data[(startY * imageData.width + startX) * 4] ?? 0) + blockSize
}

function detectEdges(
  imageData: ImageData,
  startX: number,
  startY: number,
  blockSize: number,
): number {
  return ((imageData.width + imageData.height + startX + startY + blockSize) % 100) / 100
}
