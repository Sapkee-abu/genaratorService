15. ส่วนที่อยากให้จำที่สุด

ถ้าอธิบายสั้น ๆ ให้คนอื่นฟัง ให้พูดแบบนี้:

Agent เป็นคนบอกว่าต้องการข้อมูลอะไร

Master เป็นคนเตรียมช่องทางให้ Retrieval Manager ไปค้นข้อมูลผ่าน MCP

Retrieval Manager เป็นคนเลือกว่าจะลองค้นจาก Chroma, Mongo หรือ Document/OCR

Function ที่ Master inject ให้เป็นสะพานไปหา MCP Client

ClientSession คือ MCP Client ที่ส่งคำขอไป MCP Server

MCP Server รับคำขอ แล้วเลือก MCP Tool ที่ตรงกับชื่อที่ส่งมา

MCP Tool เป็นตัวเรียก module ที่เข้าถึง Data Source จริง เช่น MongoDB หรือ ChromaDB

เมื่อได้ข้อมูลแล้ว ข้อมูลก็วิ่งย้อนกลับทางเดิมจนถึง Agent



แต่ Document/OCR ตอนนี้ยังไม่ได้ทำงานจริง

ใน source retrieval/document_ocr.py มีเพียง:

async def search(item):
    return []

ดังนั้นตอนนี้พูดกับอาจารย์ได้ว่า:

"ระบบออกแบบให้มี Document/OCR เป็น retrieval tier ที่สาม แต่ implementation ปัจจุบันยังเป็น stub และยังไม่มี OCR pipeline จริง"