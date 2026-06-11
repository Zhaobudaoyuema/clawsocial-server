export const ALLOWED_EXTENSIONS = [
  '.pdf',
  '.docx',
  '.xlsx',
  '.pptx',
  '.html',
  '.htm',
  '.csv',
  '.txt',
  '.md',
] as const

export const ACCEPT_ATTR = ALLOWED_EXTENSIONS.join(',')

export const FORMAT_HINT = 'PDF、Word、Excel、PPT、HTML、CSV、TXT、Markdown'

export function validateDeidFile(file: File): string | null {
  const name = file.name.toLowerCase()
  const ok = ALLOWED_EXTENSIONS.some((ext) => name.endsWith(ext))
  if (!ok) {
    return `不支持的格式，请上传：${FORMAT_HINT}`
  }
  return null
}

const FORMAT_LABELS: Record<string, string> = {
  pdf: 'PDF',
  docx: 'Word',
  xlsx: 'Excel',
  pptx: 'PPT',
  html: 'HTML',
  htm: 'HTML',
  csv: 'CSV',
  txt: 'TXT',
  md: 'Markdown',
}

export function sourceFormatLabel(filename: string): string {
  const ext = filename.includes('.') ? filename.split('.').pop()?.toLowerCase() || '' : ''
  return FORMAT_LABELS[ext] || ext.toUpperCase() || '文档'
}

export type SourceMarkdownPayload = {
  original_filename: string
  source_format: string
  source_format_label: string
  file_type: string
  truncated: boolean
  stats: {
    char_count: number
    line_count: number
    paragraph_count: number
    table_count: number
  }
  content: string
}
