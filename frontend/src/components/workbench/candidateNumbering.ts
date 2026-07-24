import type { ReviewItem } from "../../api/types";


export function deriveCandidateNumbers(
  items: readonly ReviewItem[],
): ReadonlyMap<string, number> {
  const numbers = new Map<string, number>();
  for (const item of items) {
    if (item.active) numbers.set(item.item_id, numbers.size + 1);
  }
  return numbers;
}
