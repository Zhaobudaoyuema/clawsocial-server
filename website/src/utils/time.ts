const BEIJING_TIMEZONE = 'Asia/Shanghai'

const beijingTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: BEIJING_TIMEZONE,
  hour12: false,
  hour: '2-digit',
  minute: '2-digit',
})

const beijingDateFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: BEIJING_TIMEZONE,
  month: 'numeric',
  day: 'numeric',
})

const beijingDateTimeFormatter = new Intl.DateTimeFormat('zh-CN', {
  timeZone: BEIJING_TIMEZONE,
  hour12: false,
  year: 'numeric',
  month: '2-digit',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

function toDate(input: string | Date): Date {
  return input instanceof Date ? input : new Date(input)
}

export function formatBeijingTime(input: string | Date): string {
  return beijingTimeFormatter.format(toDate(input))
}

export function formatBeijingDate(input: string | Date): string {
  return beijingDateFormatter.format(toDate(input))
}

export function formatBeijingDateTime(input: string | Date): string {
  return beijingDateTimeFormatter.format(toDate(input)).replace(/\//g, '-')
}
