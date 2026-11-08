import type { ReferenceApi } from "../contracts";
import type { ReferenceItem, ReferenceTree } from "../../types/reference";

const REFERENCE_ITEMS: Record<string, ReferenceItem> = {
  "ps.table1_1.name": {
    id: "ps.table1_1.name",
    field: "ชื่อ-นามสกุล",
    value: "ดร.พีรวิชญ์ เควด",
    source: "mongodb",
    sourceReference: { collection: "persons", personId: "6ab0fb633ca5c474ff43f8dc" },
  },
  "ps.table1_1.education_level": {
    id: "ps.table1_1.education_level",
    field: "วุฒิการศึกษาสูงสุด",
    value: "ปริญญาเอก",
    source: "chroma",
    sourceReference: { documentId: "6ab0f063f110267676bffbc2", page: 3, chunkIndex: 2 },
  },
  "ps.table1_2.work_2565": {
    id: "ps.table1_2.work_2565",
    field: "ผลงานปี 2565",
    value: "2",
    source: "mongodb",
    sourceReference: { collection: "academic_works", personId: "6ab0fb633ca5c474ff43f8dc" },
  },
  "ps.table1_2.checkbox": {
    id: "ps.table1_2.checkbox",
    field: "checkbox (อาจารย์ผู้รับผิดชอบหลักสูตร)",
    value: "ปริญญาโท",
    source: "user_edit",
    originalSourceValue: "ปริญญาเอก",
    sourceReference: { collection: "appointments" },
  },
  "ps.narrative.intro": {
    id: "ps.narrative.intro",
    field: "intro_ps",
    value: "หลักสูตรมีการดำเนินงานตามเกณฑ์มาตรฐาน...",
    source: "chroma",
    sourceReference: { documentId: "6ab68455ba16933d15598d55", page: 1, chunkIndex: 1 },
  },
};

const TREE: ReferenceTree = {
  criterion: "root",
  nodes: [
    {
      id: "ps",
      label: "PS",
      children: [
        {
          id: "ps.table1_1",
          label: "Table 1.1",
          children: [
            { id: "ps.table1_1.name", label: "ชื่อ-นามสกุล", referenceItemId: "ps.table1_1.name" },
            {
              id: "ps.table1_1.education_level",
              label: "วุฒิการศึกษาสูงสุด",
              referenceItemId: "ps.table1_1.education_level",
            },
          ],
        },
        {
          id: "ps.table1_2",
          label: "Table 1.2",
          children: [
            { id: "ps.table1_2.work_2565", label: "ผลงานปี 2565", referenceItemId: "ps.table1_2.work_2565" },
            { id: "ps.table1_2.checkbox", label: "checkbox", referenceItemId: "ps.table1_2.checkbox" },
          ],
        },
        {
          id: "ps.narrative",
          label: "Narrative",
          children: [{ id: "ps.narrative.intro", label: "intro_ps", referenceItemId: "ps.narrative.intro" }],
        },
      ],
    },
    { id: "p1", label: "P1", children: [] },
    { id: "p2", label: "P2", children: [] },
    { id: "p3", label: "P3", children: [] },
    { id: "p4", label: "P4", children: [] },
    { id: "p8", label: "P8", children: [] },
  ],
};

export const mockReferenceApi: ReferenceApi = {
  async getReferenceTree() {
    return TREE;
  },

  async getReferenceItem(id: string) {
    const item = REFERENCE_ITEMS[id];
    if (!item) throw new Error("ไม่พบ Reference สำหรับ field นี้");
    return item;
  },
};
