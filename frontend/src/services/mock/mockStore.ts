/** Shared in-memory state for the mock adapters only (services/mock/*) -
 * lets a mock Download in generatorApi show up in mock History immediately,
 * the same way the real Backend's generated_documents collection would.
 * Never imported by services/api/* or by any component directly. */

export interface MockVersionRecord {
  version: number;
  timestamp: string;
  fileType: string;
  html: string;
}

const FILE_NAME = "SAR_2569.docx";
const versions: MockVersionRecord[] = [];

export function getFileName(): string {
  return FILE_NAME;
}

export function listVersions(): MockVersionRecord[] {
  return [...versions].sort((a, b) => b.version - a.version);
}

export function getVersion(version: number): MockVersionRecord | undefined {
  return versions.find((v) => v.version === version);
}

export function addVersion(html: string): MockVersionRecord {
  const record: MockVersionRecord = {
    version: versions.length + 1,
    timestamp: new Date().toISOString(),
    fileType: "docx",
    html,
  };
  versions.push(record);
  return record;
}
