import type { HistoryApi } from "../contracts";
import type { GeneratedDocument } from "../../types/document";
import { getFileName, getVersion, listVersions } from "./mockStore";

export const mockHistoryApi: HistoryApi = {
  async getHistory() {
    return {
      fileName: getFileName(),
      versions: listVersions().map(({ version, timestamp, fileType }) => ({ version, timestamp, fileType })),
    };
  },

  async previewVersion(version: number): Promise<GeneratedDocument> {
    const record = getVersion(version);
    if (!record) throw new Error(`ไม่พบ Version ${version}`);
    return {
      id: `version-${version}`,
      fileName: getFileName(),
      html: record.html,
      status: "saved",
      lastSavedAt: record.timestamp,
    };
  },

  async downloadVersion(version: number): Promise<Blob> {
    const record = getVersion(version);
    if (!record) throw new Error(`ไม่พบ Version ${version}`);
    return new Blob([record.html], { type: "application/octet-stream" });
  },
};
