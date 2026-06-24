import hljs from 'highlight.js'
import { marked } from 'marked'

marked.use({
  renderer: {
    code({ text, lang }: { text: string; lang?: string }) {
      const language = lang && hljs.getLanguage(lang) ? lang : 'plaintext'
      const highlighted = hljs.highlight(text, { language }).value
      return `<pre><code class="language-${language}">${highlighted}</code></pre>`
    },
  },
})

export function renderMarkdown(markdown: string): string {
  const html = marked(markdown) as string
  return html.replace(
    /<pre><code class="language-(\w+)">(.*?)<\/code><\/pre>/gs,
    '<div class="code-block"><pre><code class="language-$1">$2</code></pre></div>',
  )
}

export function sanitizeHtml(html: string): string {
  return html.replace(/<script[^>]*>.*?<\/script>/gis, '')
}

export function safeRenderMarkdown(markdown: string): string {
  return sanitizeHtml(renderMarkdown(markdown))
}

export function setupCodeCopyFunction() {
  if (typeof window !== 'undefined') {
    ;(window as unknown as Record<string, unknown>).copyCodeToClipboard = (button: HTMLElement) => {
      const code = button.getAttribute('data-code') ?? ''
      return navigator.clipboard.writeText(code)
    }
  }
}
