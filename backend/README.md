# LectureMind Backend

FastAPI backend implementing the LectureMind pipeline: FFmpeg audio extraction,
faster-whisper transcription, transcript cleaning, timestamp-aware chunking,
Sentence-Transformers embeddings, ChromaDB indexing, RAG-based chatbot,
hierarchical summarization and keyword extraction.

## Run

```
python -m venv venv
venv\Scripts\activate        (Windows)
pip install -r requirements.txt
copy ..\.env.example .env
uvicorn app.main:app --reload
```

API docs available at http://localhost:8000/docs once running.

See the root README.md for full installation and usage instructions.
