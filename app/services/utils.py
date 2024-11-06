import os
from typing import Optional, List
import asyncio
from app.services.livkit_rag import process_files

def extract_text_from_file(filename: str, content: bytes) -> Optional[str]:
    _, ext = os.path.splitext(filename)
    ext = ext.lower()
    if ext == ".txt":
        return content.decode("utf-8")
    elif ext == ".pdf":
        # Implement PDF text extraction
        from io import BytesIO
        from PyPDF2 import PdfReader
        reader = PdfReader(BytesIO(content))
        text = ""
        for page in reader.pages:
            text += page.extract_text()
        return text
    elif ext == ".docx":
        # Implement DOCX text extraction
        from io import BytesIO
        import docx
        doc = docx.Document(BytesIO(content))
        text = "\n".join([para.text for para in doc.paragraphs])
        return text
    else:
        return None

def delete_directory(path: str):
    import shutil
    if os.path.exists(path):
        shutil.rmtree(path)

async def re_embed_files(agent_dir: str, filenames: List[str]):
    files_dir = os.path.join(agent_dir, "files")
    combined_text = ""
    for filename in filenames:
        file_path = os.path.join(files_dir, filename)
        with open(file_path, "rb") as f:
            content = f.read()
            text = extract_text_from_file(filename, content)
            if text:
                combined_text += text + "\n"

    # Save raw data
    raw_data_file = os.path.join(agent_dir, "raw_data.txt")
    with open(raw_data_file, "w") as f:
        f.write(combined_text)

    # Re-process the files using Livkit code
    await process_files(raw_data_file, agent_dir)
