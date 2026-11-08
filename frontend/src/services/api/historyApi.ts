import type { HistoryApi } from "../contracts";
import type { GeneratedDocument } from "../../types/document";
import { getBlob, getJson } from "../httpClient";

/** Real backend: GET /api/history, GET /api/history/{version}/preview,
 * GET /api/history/{version}/download - all sourced from
 * generated_documents (Download-created Version Snapshots only). */
export const realHistoryApi: HistoryApi = {
  async getHistory() {
    return getJson("/api/history");
  },

  async previewVersion(version: number): Promise<GeneratedDocument> {
    const { html } = await getJson<{ html: string }>(`/api/history/${version}/preview`);
    return {
      id: `version-${version}`,
      fileName: `SAR_v${version}.docx`,
      html,
      status: "saved",
    };
  },

  async downloadVersion(version: number): Promise<Blob> {
    const { blob } = await getBlob(`/api/history/${version}/download`);
    return blob;
  },
};
