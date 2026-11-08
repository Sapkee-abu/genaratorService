export type ReferenceSourceType = "chroma" | "mongodb" | "document_ocr" | "user_edit";

export interface OriginalDocumentReference {
  documentId: string;
  fileName: string;
  pageNumbers?: number[];
}

export interface SourceReference {
  documentId?: string;
  page?: number;
  chunkIndex?: number;
  collection?: string;
  personId?: string;
  /** id of the MongoDB record (any collection) - personId is only set when collection === "persons". */
  recordId?: string;
  /** Imported original files that produced this Chroma chunk or MongoDB record. */
  originalDocuments?: OriginalDocumentReference[];
}

export interface ReferenceItem {
  id: string;
  field: string;
  value: string;
  source: ReferenceSourceType;
  sourceReference?: SourceReference;
  /** Present only when the field is built from SEVERAL source records (e.g. Table 1.2's education list):
   * every one of them, in display order. `sourceReference` stays the first. */
  sourceReferences?: SourceReference[];
  /** create.md sec.23 - when a user edits a value, the original source
   * value must stay visible separately, never overwritten. */
  originalSourceValue?: string;
  /** Real backend (fix.md sec.12/13): present only when the user edited this
   * field in the Version. `source`/`sourceReference` stay the ORIGINAL source
   * (MongoDB/Chroma...) when a real mapping exists; `source === "user_edit"`
   * (with no sourceReference) when the edit has no real source mapping.
   * `value` === `currentValue`. */
  userEdited?: boolean;
  originalValue?: string;
  currentValue?: string;
}

export interface ReferenceTreeNode {
  id: string;
  label: string;
  children?: ReferenceTreeNode[];
  /** Present only on leaf nodes that map to one field's reference detail. */
  referenceItemId?: string;
}

export interface ReferenceTree {
  criterion: string;
  nodes: ReferenceTreeNode[];
}
