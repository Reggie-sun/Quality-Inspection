export type ItemRelation = {
  itemId?: string;
  itemIds?: string[];
};


export function relatedItemIds(relation: ItemRelation): string[] {
  if (relation.itemIds !== undefined) return [...relation.itemIds];
  return relation.itemId === undefined ? [] : [relation.itemId];
}


export function selectedRelation(
  relation: ItemRelation,
  selectedItemId: string | undefined,
): boolean {
  return selectedItemId !== undefined && relatedItemIds(relation).includes(selectedItemId);
}


export function selectRelationItem(
  relation: ItemRelation,
  selectedItemId: string | undefined,
): string | undefined {
  const itemIds = relatedItemIds(relation);
  if (selectedItemId !== undefined && itemIds.includes(selectedItemId)) {
    return selectedItemId;
  }
  return itemIds[0];
}
