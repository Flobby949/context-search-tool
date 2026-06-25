declare module 'qrcode-reader' {
  interface QrReaderResult {
    result?: string
  }

  class QrReader {
    callback: (error: unknown, result?: QrReaderResult) => void
    decode(imageData: ImageData): void
  }

  export = QrReader
}
