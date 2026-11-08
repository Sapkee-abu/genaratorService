# บทที่ 2 การทบทวนวรรณกรรม

> หมายเหตุก่อนใช้งาน: เนื้อหาด้านล่างเป็น **draft โครงร่าง + เนื้อหาเริ่มต้น** ที่เชื่อมโยงกับระบบจริงที่พัฒนาในโปรเจกต์นี้ (Generator Service — ระบบช่วยจัดทำรายงานการประเมินตนเอง/SAR ตามเกณฑ์ AUN-QA ด้วย Multi-Agent + RAG)
> แหล่งอ้างอิงทั้งหมดที่ใส่ไว้เป็นแหล่งที่ตรวจสอบแล้วว่ามีอยู่จริง (ค้นผ่านเว็บ ณ วันที่เขียน) แต่:
> - ควรเปิดอ่านฉบับเต็มเองอีกครั้งก่อนอ้างอิงจริงในเล่ม (กันกรณีตีความเนื้อหาผิดจาก snippet ที่สรุปมา)
> - ควรปรับรูปแบบการอ้างอิง (APA/IEEE/ตามที่สถาบันกำหนด) และเพิ่มงานวิจัยภาษาไทย/ของสถาบันตัวเองจาก ThaiLIS หรือห้องสมุดมหาวิทยาลัย โดยเฉพาะหัวข้อ AUN-QA/SAR ที่เกี่ยวกับบริบทไทยโดยตรง เพราะสิ่งที่ค้นได้นี้เป็นงานทั่วไป/ต่างประเทศเป็นหลัก
> - ห้ามคัดลอกคำต่อคำจากบทคัดย่อที่สรุปไว้ — ใช้เป็นแนวทางแล้วเขียนด้วยคำของตัวเองตามหลักวิชาการ

---

## 2.1 ทฤษฎีที่เกี่ยวข้อง

### 2.1.1 ปัญญาประดิษฐ์เชิงรู้สร้างและโมเดลภาษาขนาดใหญ่ (Generative AI และ Large Language Model)
อธิบายแนวคิดโมเดลภาษาขนาดใหญ่ (LLM) ที่สร้างจากสถาปัตยกรรม Transformer (Vaswani et al., 2017) ซึ่งใช้กลไก self-attention ในการเรียนรู้ความสัมพันธ์ของคำในบริบทยาว ทำให้โมเดลสามารถสร้างข้อความต่อเนื่อง (text generation) ที่สอดคล้องกับบริบทได้ ในระบบที่พัฒนา ใช้ LLM (Google Gemini) เป็นแกนของ Criterion Agent ในการสร้างเนื้อหาเชิงบรรยาย (narrative) ของแต่ละเกณฑ์ประเมิน (`backend/common/gemini.py`, `backend/criterion_agents/*/agent.py`)

### 2.1.2 การค้นคืนแบบเสริมการสร้างข้อความ (Retrieval-Augmented Generation — RAG)
RAG เป็นแนวคิดที่เสนอโดย Lewis et al. (2020) เพื่อแก้ปัญหาที่ LLM ตอบจาก "ความจำ" ภายในพารามิเตอร์เพียงอย่างเดียว ซึ่งอาจล้าสมัยหรือไม่ครอบคลุมความรู้เฉพาะด้าน โดยแนวคิด RAG คือการค้นคืนเอกสาร/ข้อมูลที่เกี่ยวข้องจากฐานข้อมูลภายนอกก่อน แล้วนำมาเป็นบริบท (context) ให้ LLM ใช้สร้างคำตอบ ทำให้คำตอบมีหลักฐานอ้างอิงที่ตรวจสอบได้ (traceable) ระบบที่พัฒนาใช้แนวคิดนี้เป็นหัวใจของ Retrieval Manager (`backend/retrieval/manager.py`) ซึ่งค้นข้อมูลจาก 3 ชั้น (ChromaDB → MongoDB → Document/OCR) ก่อนส่งให้ Criterion Agent สร้างเนื้อหา

### 2.1.3 การฝังเวกเตอร์เชิงความหมายและการค้นคืนแบบเวกเตอร์ (Semantic Embedding & Vector Search)
ทฤษฎีการแทนข้อความด้วยเวกเตอร์ (embedding) ในปริภูมิเชิงความหมาย (semantic space) ทำให้สามารถวัดความคล้ายของเนื้อหาด้วยค่าคล้ายเชิงมุม (cosine similarity) แทนการจับคู่คำตรงตัว โมเดล BGE-M3 (BAAI, 2024) เป็นโมเดลฝังเวกเตอร์หลายภาษาที่รองรับการค้นคืนแบบ dense/multi-vector/sparse ในคราวเดียว ระบบที่พัฒนาใช้ BGE-M3 ฝัง query (`backend/common/bge_embedding.py`) แล้วค้นคืนจาก ChromaDB (`backend/common/chroma.py`) เพื่อหาหลักฐานเชิงเนื้อหา (evidence chunk) ที่ใกล้เคียงกับสิ่งที่ Criterion Agent ต้องการ

### 2.1.4 ระบบหลายเอเจนต์ (Multi-Agent System)
แนวคิดการแบ่งงานซับซ้อนให้ agent ที่มีหน้าที่/ความรับผิดชอบเฉพาะทาง (specialized agent) ทำงานร่วมกันภายใต้ orchestrator กลาง งานวิจัยที่ใกล้เคียงโดยตรงคือ Musumeci et al. (2024) ซึ่งเสนอ multi-agent LLM สำหรับสร้างเอกสารกึ่งทางการ (semi-structured document) จาก template ในบริบทงานราชการ ระบบที่พัฒนาออกแบบตามหลักการนี้: Master Agent (`backend/master_agent/master.py`) เป็น orchestrator ที่ไม่สร้างเนื้อหาเอง แต่กระจายงานให้ Criterion Agent เฉพาะทางของแต่ละเกณฑ์ (PS/P1/P2/P3/P4/P8 ใน `backend/criterion_agents/`)

### 2.1.5 ปัญหาการสร้างข้อมูลเท็จของ LLM และการตรวจสอบความถูกต้อง (Hallucination & Verification/Grounding)
Hallucination คือปรากฏการณ์ที่ LLM สร้างข้อความที่ฟังดูสมเหตุสมผลแต่ไม่ตรงกับความเป็นจริงหรือหลักฐานที่มีอยู่ (Ji et al., 2023) งานวิจัยสายการตรวจสอบการอ้างอิง (citation verification) ชี้ว่า LLM มีแนวโน้มสร้างการอ้างอิงที่ไม่ตรงกับหลักฐานจริงในสัดส่วนสูง จึงต้องมีกลไกตรวจสอบเพิ่ม เช่น VeriCite และ CiteGuard ที่ใช้โมเดลตรวจสอบความสอดคล้องเชิงตรรกะ (NLI) ยืนยัน claim กับหลักฐานก่อนยอมรับคำตอบ ระบบที่พัฒนามีกลไกคล้ายกันคือ Verification Gate (`backend/common/verification.py`) ที่ตรวจ 3 เงื่อนไข: (1) citation ตรงกับข้อความหลักฐานจริงด้วย fuzzy matching (2) ความคล้ายเชิงความหมายระหว่างเนื้อหาที่สร้างกับหลักฐาน (3) ความครบถ้วนของการอ้างอิง — ถ้าไม่ผ่านจะส่งกลับให้ Agent เดิมสร้างใหม่ (retry) ไม่ปล่อยเข้า Template Injection

### 2.1.6 กรอบการประกันคุณภาพการศึกษาระดับหลักสูตรของเครือข่ายมหาวิทยาลัยอาเซียน (AUN-QA)
AUN-QA (ASEAN University Network Quality Assurance) เป็นกรอบมาตรฐานการประกันคุณภาพระดับหลักสูตรที่เครือข่ายมหาวิทยาลัยอาเซียนกำหนด ฉบับปัจจุบัน (Version 4.0, 2020) ประกอบด้วย 8 เกณฑ์หลัก การจัดทำรายงานการประเมินตนเอง (Self-Assessment Report — SAR) ตามเกณฑ์นี้เป็นกระบวนการที่ใช้แรงงานคนสูงและต้องอ้างอิงหลักฐานจากหลายแหล่งข้อมูล (บุคคล คุณวุฒิ ผลงานวิชาการ ฯลฯ) ระบบที่พัฒนาออกแบบ Criterion Agent ให้สอดคล้องกับโครงสร้างเกณฑ์นี้โดยตรง (เช่น PS = Programme Specification/บุคลากร)

### 2.1.7 สถาปัตยกรรมไคลเอนต์–เซิร์ฟเวอร์สำหรับเชื่อมโมเดลภาษากับเครื่องมือภายนอก (Model Context Protocol)
Model Context Protocol (MCP) เป็นมาตรฐานเปิดที่ Anthropic เผยแพร่ในปี 2024 เพื่อกำหนดรูปแบบการสื่อสารมาตรฐานระหว่าย AI agent กับเครื่องมือ/แหล่งข้อมูลภายนอก ผ่านสถาปัตยกรรม client–server ที่ชัดเจน (tool discovery, tool invocation) ระบบที่พัฒนาใช้ MCP เป็นขอบเขตบังคับ (architecture boundary) ที่ทำให้ Master Agent/Retrieval Manager ไม่แตะ MongoDB/ChromaDB ตรง ต้องผ่าน MCP Server (`backend/mcp_server/server.py`) เสมอ — เป็นการแยกชั้นความรับผิดชอบ (separation of concerns) ตามทฤษฎีสถาปัตยกรรมซอฟต์แวร์

---

## 2.2 เทคโนโลยีที่เกี่ยวข้อง

| เทคโนโลยี | บทบาทในทฤษฎี/อุตสาหกรรม | การใช้งานจริงในระบบ |
|---|---|---|
| Python + FastAPI | ภาษาและเฟรมเวิร์กสร้าง REST API แบบ async ประสิทธิภาพสูง | `backend/api_server.py`, `backend/api/routes.py` |
| MongoDB (ผ่าน Motor) | ฐานข้อมูล NoSQL เชิงเอกสาร เหมาะกับข้อมูลโครงสร้างไม่คงที่ | เก็บ persons/educations/appointments/academic_works และ Version Snapshot (`backend/common/mongo.py`) |
| ChromaDB | ฐานข้อมูลเวกเตอร์ (vector database) สำหรับค้นคืนเชิงความหมาย | เก็บ document chunk ที่ฝังเวกเตอร์แล้ว, ค้นด้วย cosine similarity (`backend/common/chroma.py`) |
| Google Gemini API | บริการ LLM เชิงพาณิชย์สำหรับสร้างข้อความ/JSON | สร้างเนื้อหาเชิงบรรยายของ Criterion Agent (`backend/common/gemini.py`) |
| BGE-M3 / sentence-transformers | โมเดลฝังเวกเตอร์หลายภาษา (multilingual embedding) | ฝัง query ก่อนค้น ChromaDB (`backend/common/bge_embedding.py`) |
| python-docx | ไลบรารีจัดการไฟล์ Word (.docx) ระดับ OOXML | parse/inject/save เอกสาร SAR โดยรักษาโครงสร้างเดิม (`backend/master_agent/docx_utils.py`, `template_injector.py`) |
| Model Context Protocol SDK | มาตรฐานเปิดสำหรับ client-server ของ AI tool | `backend/master_agent/master.py` (client), `backend/mcp_server/server.py` (server) |
| React + TypeScript + Vite | เฟรมเวิร์กและ build tool สำหรับ SPA ฝั่ง frontend | `frontend/src/` ทั้งหมด (หน้า Generate/History/Reference) |
| REST API (JSON over HTTP) | มาตรฐานการสื่อสารระหว่าง frontend–backend | ทุก endpoint ใน `backend/api_server.py`/`backend/api/routes.py` |

---

## 2.3 งานวิจัยหรือระบบที่ใกล้เคียง

### 2.3.1 งานวิจัยด้าน RAG เพื่อลดปัญหาการสร้างข้อมูลเท็จและเพิ่มความน่าเชื่อถือของการอ้างอิง
งานวิจัยสายนี้ชี้ให้เห็นว่าแม้ RAG จะช่วยลด hallucination ได้ แต่ LLM ยังมีแนวโน้มสร้างการอ้างอิง (citation) ที่ไม่ตรงกับหลักฐานจริงในสัดส่วนสูง (บางงานวิจัยรายงานว่าสูงถึง 78–90% ของกรณี) จึงมีข้อเสนอกลไกตรวจสอบเพิ่มเติม เช่น
- "On the Capacity of Citation Generation by Large Language Models" (2024) เสนอวิธี Generate-then-Refine เพื่อแก้ไขการอ้างอิงที่ผิดโดยไม่แก้เนื้อความ
- VeriCite (SIGIR-AP 2025) ใช้โมเดล NLI ตรวจสอบหลักฐานแบบ 3 ขั้นตอนก่อนยอมรับการอ้างอิง
- CiteGuard เสนอ agent-based framework ตรวจสอบความสอดคล้องของการอ้างอิงกับต้นฉบับ

แนวทางเหล่านี้สอดคล้องกับ Verification Gate ของระบบที่พัฒนา แต่ระบบนี้ใช้วิธีที่เบากว่า (fuzzy text matching + semantic similarity threshold) แทนโมเดล NLI แยกต่างหาก ซึ่งเป็นจุดที่สามารถอภิปรายเป็นข้อจำกัด/โอกาสพัฒนาต่อในบทสรุปได้

### 2.3.2 งานวิจัยด้านระบบหลายเอเจนต์สำหรับสร้างเอกสารจาก Template โครงสร้างกึ่งทางการ
Musumeci et al. (2024) เสนอ multi-agent framework สำหรับงานราชการ (public administration) ที่ประกอบด้วย Semantics Identification Agent, Information Retrieval Agent, และ Content Generation Agent ทำงานร่วมกันสร้างเอกสารให้ตรงโครงสร้างที่กำหนด — เป็นงานวิจัยที่ **ใกล้เคียงกับระบบที่พัฒนาที่สุด** ในเชิงแนวคิดสถาปัตยกรรม ต่างกันที่ระบบนี้ (ก) ผูกแต่ละ agent เข้ากับเกณฑ์ประเมินคุณภาพการศึกษาที่มีข้อกำหนดเฉพาะเจาะจง (ข) รักษาโครงสร้าง OOXML เดิมของ Word (merged cell, checkbox, การจัดรูปแบบ) แทนการสร้างเอกสารใหม่ และ (ค) มี Verification Gate แยกเฉพาะก่อนฉีดข้อมูลเข้าเอกสาร

### 2.3.3 ความพยายามพัฒนาระบบสนับสนุนการจัดทำ SAR ตามเกณฑ์ AUN-QA
จากการสำรวจพบว่ากระบวนการประเมิน AUN-QA ในปัจจุบันยังพึ่งพาการตีความเอกสารโดยมนุษย์เป็นหลัก ทำให้เกิดความไม่สอดคล้องระหว่างผู้ประเมิน มีงานวิจัย/วิทยานิพนธ์ในบริบทไทยและเวียดนามที่ศึกษาการออกแบบ **Information System/Data Relationship Structure** สำหรับรวบรวมข้อมูลเพื่อจัดทำ SAR ตามเกณฑ์ AUN-QA (เช่น งานในวารสาร TCI-Thaijo ที่ค้นพบ) แต่งานเหล่านี้ส่วนใหญ่เน้นการ "จัดเก็บ/เชื่อมโยงข้อมูล" ผ่าน API เพื่อลดภาระงานธุรการ **ยังไม่พบงานที่ใช้ LLM สร้างเนื้อหาเชิงบรรยายพร้อมหลักฐานอ้างอิงที่ตรวจสอบได้โดยอัตโนมัติ** ซึ่งเป็นช่องว่างที่ระบบนี้พยายามเติมเต็ม

ในภาคอุตสาหกรรม พบตัวอย่างการใช้ AI agent ช่วยงานด้านรายงานคุณภาพในวงกว้างกว่า (ไม่เฉพาะ AUN-QA) เช่น การใช้ Amazon Bedrock ช่วยจัดทำรายงานของหน่วยงานกำกับคุณภาพการศึกษาบาห์เรน (BQA) ซึ่งเป็น use case เชิงพาณิชย์มากกว่างานวิจัยเชิงวิชาการ ควรอ้างอิงด้วยความระมัดระวังในบทนี้ (ระบุให้ชัดว่าเป็น industry case ไม่ใช่ peer-reviewed research)

### 2.3.4 สรุปช่องว่างงานวิจัย (Research Gap) ที่ระบบนี้นำเสนอ
จากการทบทวนข้างต้น สรุปได้ว่างานที่มีอยู่แยกกันเป็น 3 กลุ่มที่ไม่มีงานใดครอบคลุมครบ: (1) งานวิจัย RAG/citation-verification ที่เน้นความถูกต้องของการอ้างอิงแต่ไม่ได้ผูกกับโดเมนรายงานประกันคุณภาพ (2) งานระบบสนับสนุน SAR/AUN-QA ที่เน้นจัดเก็บ-เชื่อมโยงข้อมูลแต่ไม่มีการสร้างเนื้อหาด้วย LLM (3) งาน multi-agent document generation ทั่วไปที่ไม่ได้ออกแบบมารักษาโครงสร้างต้นฉบับ Word ระดับ OOXML (merged cell/checkbox) และไม่มี verification gate เฉพาะก่อนฉีดข้อมูล ระบบ Generator Service ที่พัฒนาในวิทยานิพนธ์นี้จึงเสนอการผสานทั้งสามมิติเข้าด้วยกัน: multi-agent ต่อเกณฑ์ + RAG สามชั้น (vector → structured DB → OCR fallback) + verification gate ก่อน inject + การฉีดข้อมูลที่รักษาโครงสร้างเอกสารต้นฉบับ + ระบบ Web สำหรับทบทวน/แก้ไข/บันทึกเวอร์ชันที่ตรวจสอบย้อนกลับได้ (traceability)

---

## รายการอ้างอิง (ตัวอย่าง — ปรับรูปแบบตามที่สถาบันกำหนด)

1. Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). Attention is all you need. *Advances in Neural Information Processing Systems, 30*.
2. Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., & Kiela, D. (2020). Retrieval-augmented generation for knowledge-intensive NLP tasks. *Advances in Neural Information Processing Systems, 33*. https://arxiv.org/abs/2005.11401
3. BAAI (Beijing Academy of Artificial Intelligence). (2024). *BGE M3-Embedding: Multi-lingual, multi-functionality, multi-granularity text embeddings through self-knowledge distillation* [Model documentation]. https://huggingface.co/BAAI/bge-m3
4. Musumeci, E., Brienza, M., Suriani, V., Nardi, D., & Bloisi, D. D. (2024). *LLM based multi-agent generation of semi-structured documents from semantic templates in the public administration domain*. arXiv. https://arxiv.org/abs/2402.14871
5. Ji, Z., Lee, N., Frieske, R., Yu, T., Su, D., Xu, Y., Ishii, E., Bang, Y. J., Madotto, A., & Fung, P. (2023). Survey of hallucination in natural language generation. *ACM Computing Surveys, 55*(12). https://arxiv.org/abs/2202.03629
6. ASEAN University Network. (2020). *Guide to AUN-QA assessment at programme level* (Version 4.0). ASEAN University Network.
7. Anthropic. (2024). *Model Context Protocol specification*. https://modelcontextprotocol.io
8. (เพิ่มงานวิจัย citation-verification ที่เกี่ยวข้อง เช่น VeriCite (SIGIR-AP 2025), CiteGuard — ค้นฉบับเต็มเพื่ออ้างอิงให้ครบ author/venue ก่อนใส่ในเล่มจริง)
9. (เพิ่มงานวิจัย/วิทยานิพนธ์ภาษาไทยเรื่องระบบสนับสนุนการจัดทำ SAR ตาม AUN-QA จาก ThaiLIS ให้ตรงกับสถาบันของตนเอง)
