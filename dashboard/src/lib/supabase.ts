import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL
const supabaseKey = import.meta.env.VITE_SUPABASE_ANON_KEY

export const supabase = createClient(supabaseUrl, supabaseKey)

/**
 * Fetch all rows from a query, paginating automatically.
 * Supabase default limit is 1000 — this fetches in batches.
 */
export async function fetchAllRows<T = Record<string, unknown>>(
  buildQuery: (from: ReturnType<typeof supabase.from>) => any,
  table: string,
  pageSize = 1000,
): Promise<T[]> {
  const allRows: T[] = []
  let offset = 0
  while (true) {
    const query = buildQuery(supabase.from(table))
    const { data } = await query.range(offset, offset + pageSize - 1)
    if (!data || data.length === 0) break
    allRows.push(...(data as T[]))
    if (data.length < pageSize) break
    offset += pageSize
  }
  return allRows
}
