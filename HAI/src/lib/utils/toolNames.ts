/**
 * Format a tool name for display when no display name is provided.
 * Converts snake_case to Title Case.
 *
 * @example formatToolNameFallback('search_regulations') => 'Search Regulations'
 */
export function formatToolNameFallback(name: string): string {
  return name
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}
