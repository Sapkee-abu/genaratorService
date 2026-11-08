/** create.md sec.16/17 - only ever populated by a real Download (Version
 * Snapshot); Save (Current Draft) never adds an entry here. Backend owns
 * version numbers - never assigned or guessed by the frontend. */
export interface DocumentVersion {
  version: number;
  timestamp: string;
  fileType: string;
}

export interface DocumentHistory {
  fileName: string;
  versions: DocumentVersion[];
}
