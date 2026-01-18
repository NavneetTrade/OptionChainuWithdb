/**
 * Time utility functions for displaying timestamps in IST (Indian Standard Time)
 */

const IST_TIMEZONE = 'Asia/Kolkata'

/**
 * Format a timestamp string to IST time
 * @param timestamp ISO timestamp string
 * @param options Intl.DateTimeFormatOptions
 * @returns Formatted time string in IST
 */
export function formatISTTime(
  timestamp: string,
  options: Intl.DateTimeFormatOptions = {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: IST_TIMEZONE,
    hour12: false
  }
): string {
  try {
    const date = new Date(timestamp)
    return new Intl.DateTimeFormat('en-IN', {
      ...options,
      timeZone: IST_TIMEZONE
    }).format(date)
  } catch (error) {
    console.error('Error formatting IST time:', error)
    return timestamp
  }
}

/**
 * Format a timestamp to IST date and time
 * @param timestamp ISO timestamp string
 * @returns Formatted date-time string in IST
 */
export function formatISTDateTime(timestamp: string): string {
  return formatISTTime(timestamp, {
    year: 'numeric',
    month: 'short',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: IST_TIMEZONE,
    hour12: false
  })
}

/**
 * Format a timestamp to IST time only (HH:MM:SS)
 * @param timestamp ISO timestamp string
 * @returns Formatted time string in IST
 */
export function formatISTTimeOnly(timestamp: string): string {
  return formatISTTime(timestamp, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: IST_TIMEZONE,
    hour12: false
  })
}

/**
 * Format a timestamp to IST time with AM/PM
 * @param timestamp ISO timestamp string
 * @returns Formatted time string in IST with AM/PM
 */
export function formatISTTimeAMPM(timestamp: string): string {
  return formatISTTime(timestamp, {
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    timeZone: IST_TIMEZONE,
    hour12: true
  }) + ' IST'
}

/**
 * Format a timestamp to IST time for chart labels (HH:MM)
 * @param timestamp ISO timestamp string
 * @returns Formatted time string in IST (HH:MM IST)
 */
export function formatISTTimeForChart(timestamp: string): string {
  return formatISTTime(timestamp, {
    hour: '2-digit',
    minute: '2-digit',
    timeZone: IST_TIMEZONE,
    hour12: false
  }) + ' IST'
}
