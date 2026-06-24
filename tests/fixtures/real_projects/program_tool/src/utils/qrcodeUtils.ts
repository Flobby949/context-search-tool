import QRCode from 'qrcode'
import QrReader from 'qrcode-reader'

export interface QRCodeOptions {
  text: string
  width?: number
  color?: {
    dark?: string
    light?: string
  }
  errorCorrectionLevel?: 'L' | 'M' | 'Q' | 'H'
}

export async function generateQRCode(options: QRCodeOptions): Promise<string> {
  if (!options.text.trim()) {
    throw new Error('QRCode text is required')
  }
  return QRCode.toDataURL(options.text, {
    width: options.width ?? 256,
    errorCorrectionLevel: options.errorCorrectionLevel ?? 'M',
    color: options.color,
  })
}

export function parseQRCode(imageData: string): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new QrReader()
    reader.callback = (error: unknown, result?: { result?: string }) => {
      if (error) {
        reject(error)
        return
      }
      resolve(result?.result ?? '')
    }
    const image = new Image()
    image.onload = () => {
      const canvas = document.createElement('canvas')
      const context = canvas.getContext('2d')
      if (!context) return reject(new Error('canvas context missing'))
      context.drawImage(image, 0, 0)
      reader.decode(context.getImageData(0, 0, canvas.width, canvas.height))
    }
    image.src = imageData
  })
}

export function parseQRCodeFromFile(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const fileReader = new FileReader()
    fileReader.onload = async () => resolve(await parseQRCode(String(fileReader.result)))
    fileReader.onerror = reject
    fileReader.readAsDataURL(file)
  })
}

export function isValidColor(color: string): boolean {
  return /^#([A-Fa-f0-9]{6}|[A-Fa-f0-9]{3})$/.test(color)
}
