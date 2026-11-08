import type { ReferenceApi } from "../contracts";
import { getJson } from "../httpClient";

/** Real backend: GET /api/reference?version=N, GET /api/reference/item/
 * {item_id}?version=N (backend/reference/traceability_api.py). Response
 * shapes already match ReferenceTree/ReferenceItem exactly - no mapping
 * needed. Source types populated with real data: chroma, mongodb.
 * document_ocr is never fabricated (no live citations yet). A Version's
 * User Edits (fix.md sec.12/13) come back as: the field's ORIGINAL source
 * unchanged + originalValue/currentValue/userEdited, or - when the edit has
 * no real source mapping - source "user_edit" with no sourceReference. */
export const realReferenceApi: ReferenceApi = {
  async getReferenceTree(version?: number) {
    const query = version !== undefined ? `?version=${version}` : "";
    return getJson(`/api/reference${query}`);
  },

  async getReferenceItem(id: string, version?: number) {
    const query = version !== undefined ? `?version=${version}` : "";
    return getJson(`/api/reference/item/${encodeURIComponent(id)}${query}`);
  },
};
