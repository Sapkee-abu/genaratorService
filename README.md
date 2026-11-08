# Generator Service — AUN-QA SAR

Generator Service สร้างร่างรายงาน SAR เป็นไฟล์ DOCX จาก Template และหลักฐานของหลักสูตร โดยเชื่อมกับ Monitor, Import/Template Service, MongoDB และ ChromaDB ผู้ใช้สามารถตรวจแก้ บันทึก ดาวน์โหลด และดูแหล่งอ้างอิงของเอกสารผ่านหน้าเว็บได้

## สถานะโค้ดในโฟลเดอร์นี้

โฟลเดอร์นี้เป็นสำเนา Generator ล่าสุดจากโปรเจกต์ 3 Service กระบวนการสร้างหลักไม่โหลด Example และไม่ส่ง Guideline ให้ Agent

การปรับนี้ยังไม่ได้ push ขึ้น GitHub และยังต้องทดสอบร่วมกับฐานข้อมูลจริง

SRS กำหนดให้ Monitor เป็นผู้ตัดสินความพร้อม และห้าม Generator ใช้ Guideline สร้างการตัดสิน Greenlight เอง การตรวจว่าโค้ดทั้งหมดตรง SRS และสร้างผลลัพธ์ได้ครบยังต้องทดสอบเพิ่มเติม

## กระบวนการทำงานโดยรวม

1. ผู้ใช้กด Generate จากหน้าเว็บ แล้ว Generator ขอผลความพร้อมจาก Monitor
2. เมื่อ Monitor ตอบว่าพร้อม Master Agent เปิด MCP Server ผ่าน stdio และโหลด Template กับ Config
3. Slot Marking Agent วิเคราะห์ตำแหน่งที่ต้องเติมใน Template
4. Criterion Agent ส่ง Data Request ให้ Retrieval Manager ค้นหลักฐานผ่าน MCP โดยลอง ChromaDB, MongoDB และ Document/OCR ตามลำดับ ทั้งนี้ OCR ในโค้ดปัจจุบันยังเป็น stub
5. Agent สร้างเนื้อหาพร้อม Citation; ตาราง PS บางส่วนคำนวณจากข้อมูลแบบมีโครงสร้างด้วย Python
6. Verification ตรวจ Citation, ความสอดคล้องกับหลักฐาน และความครบถ้วน ก่อนเติมส่วนที่ผ่านลง Template
7. ระบบสร้าง DOCX ให้ Preview และแก้ไขได้; Save เก็บ Draft ส่วน Download สร้าง Version สำหรับ History และ Reference

## โครงสร้าง

- `backend/` — FastAPI, Master Agent, MCP Server, Retrieval, Verification และการสร้าง DOCX
- `frontend/` — React และ TypeScript สำหรับ Generate, History และ Reference
- `documentMD/` และ `plugMD/` — เอกสารประกอบในสำเนาเครื่องนี้

## การเชื่อมต่อ

ตั้งค่าตัวแปรใน `backend/.env` จาก `backend/.env.example` ให้ตรงกับ MongoDB, ChromaDB, Template Service, Monitor Service และ Gemini API โดยไม่ส่งไฟล์ `.env` จริงขึ้น Git

ChromaDB ต้องใช้ embedding ที่เข้ากันกับข้อมูลที่ Import Service บันทึกไว้ (BGE-M3 ในการตั้งค่าระบบรวม) การใช้งานจริงต้องมี Template และหลักฐานในแหล่งข้อมูลที่เชื่อมต่อ

Frontend ที่รันแยกในโหมด Development เลือก Mock API เป็นค่าเริ่มต้น หากต้องการใช้ Backend จริง ให้ตั้ง `VITE_USE_MOCK_API=false` และ `VITE_API_BASE_URL` ใน `frontend/.env` แล้วเริ่ม Vite ใหม่ เมื่อใช้กับ Portal ของ 3 Service จะเลือก API จริงผ่าน Gateway ตามการตั้งค่าของ Portal

`VITE_DEV_GENERATE=false` ใช้เส้นทางปกติซึ่งตรวจ Monitor ก่อนสร้าง ส่วนโหมด Development ที่ข้าม Monitor ต้องเปิดใช้อย่างชัดเจนทั้งฝั่ง Frontend และ Backend และไม่ใช่เส้นทาง Production

## ข้อจำกัดการตรวจสอบ

ขณะปรับ README นี้ยังไม่มีฐานข้อมูลสำหรับทดสอบการเชื่อมต่อจริง โค้ดชุดรวมที่ปรับล่าสุดยังไม่ได้รับการยืนยันแบบครบวงจร และ Agent P1–P4/P8 ในชุดที่ปรับยังมี Data Request ว่าง จึงอาจไม่สามารถสร้างเนื้อหาส่วนเหล่านั้นได้ ยังไม่ควรสรุปว่าผลลัพธ์เหมือนเดิมหรือว่าระบบตรง SRS ทุกข้อจนกว่าจะพัฒนาและทดสอบเพิ่มเติม
