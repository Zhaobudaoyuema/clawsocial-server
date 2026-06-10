export const SEMANTIC_CAT_LABELS: Record<string, string> = {
  project_id: '项目编号',
  project_name: '具名项目',
  listing_code: '证券代码',
  listing_structure: '上市结构',
  data_source: '数据来源',
  deal_event: '交易事件',
  person_trait: '人员属性',
  client_hint: '客户线索',
  table_row: '表行短语',
  org_fingerprint: '机构指纹',
  person_fingerprint: '人员指纹',
  listing_fingerprint: '上市线索',
}

const LEGACY_MAP: Record<string, string> = {
  org_fingerprint: 'table_row',
  person_fingerprint: 'person_trait',
  listing_fingerprint: 'listing_code',
}

export function normalizeSemanticCategory(code: unknown): string {
  const cat = String(code || '').trim().toLowerCase()
  return LEGACY_MAP[cat] || cat
}

export function semanticCatLabel(code: unknown): string {
  const raw = String(code || '').trim().toLowerCase()
  if (!raw) return '语义'
  return SEMANTIC_CAT_LABELS[raw] || SEMANTIC_CAT_LABELS[normalizeSemanticCategory(raw)] || raw
}
