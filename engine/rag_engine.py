#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
ABOUTME: Advanced RAG capabilities using ChromaDB for handling large numbers of PDFs without character limits.
"""

import logging
import os
import shutil
from pathlib import Path
from typing import List, Optional

try:
    import chromadb
    from chromadb.config import Settings
    HAS_CHROMADB = True
except ImportError:
    HAS_CHROMADB = False

from engine.utils.document_reader import read_document

logger = logging.getLogger(__name__)

class LocalRAGIndex:
    def __init__(self, db_path: str = ".vefa_state/.chroma_db", collection_name: str = "vefa_thesis"):
        self.db_path = db_path
        self.collection_name = collection_name
        self.client = None
        self.collection = None
        self.chunks = []  # To keep compatibility with len(rag_index.chunks)
        
        if not HAS_CHROMADB:
            raise ImportError(
                "ChromaDB kurulu değil ('pip install chromadb'). Gelişmiş RAG modu bu paket "
                "olmadan çalışamaz — sessizce boş bağlam döndürmek yerine burada durduruluyor "
                "ki üst katman (varsa) düz kaynak metnine geri dönebilsin."
            )

        self._init_db()

    def _init_db(self):
        """Initialize or reset the ChromaDB persistent client."""
        # Clean up existing DB for a fresh thesis context
        if os.path.exists(self.db_path):
            try:
                import stat
                def remove_readonly(func, path, excinfo):
                    os.chmod(path, stat.S_IWRITE)
                    func(path)
                shutil.rmtree(self.db_path, onerror=remove_readonly)
            except Exception as e:
                logger.warning(f"Could not clear old ChromaDB path: {e}")

        os.makedirs(self.db_path, exist_ok=True)
        self.client = chromadb.PersistentClient(path=self.db_path, settings=Settings(anonymized_telemetry=False))
        self.collection = self.client.create_collection(
            name=self.collection_name,
            metadata={"hnsw:space": "cosine"}
        )

    def _chunk_text(self, text: str, chunk_size: int = 1500, overlap: int = 300) -> List[str]:
        """Splits text into sliding-window chunks by characters."""
        chunks = []
        start = 0
        text_len = len(text)
        
        while start < text_len:
            end = start + chunk_size
            chunk = text[start:end]
            chunks.append(chunk)
            if end >= text_len:
                break
            start += (chunk_size - overlap)
            
        return chunks

    def add_document(self, source_name: str, text: str):
        if not self.collection or not text.strip():
            return
            
        new_chunks = self._chunk_text(text)
        self.chunks.extend(new_chunks)
        
        documents = new_chunks
        start_idx = len(self.chunks) - len(new_chunks)
        ids = [f"{source_name}_chunk_{start_idx + i}" for i in range(len(new_chunks))]
        metadatas = [{"source": source_name, "chunk_index": start_idx + i} for i in range(len(new_chunks))]
        
        batch_size = 100
        for b_start in range(0, len(new_chunks), batch_size):
            b_end = b_start + batch_size
            self.collection.add(
                documents=documents[b_start:b_end],
                metadatas=metadatas[b_start:b_end],
                ids=ids[b_start:b_end]
            )

    def format_retrieved_context(self, query: str, top_k: int = 10, max_chars: int = 35000) -> str:
        """
        Queries the ChromaDB for the most relevant chunks.
        Returns a formatted string containing the top chunks.
        """
        if not self.collection or not self.chunks:
            return ""
            
        try:
            results = self.collection.query(
                query_texts=[query],
                n_results=min(top_k, len(self.chunks))
            )
            
            docs = results.get("documents", [[]])[0]
            metadatas = results.get("metadatas", [[]])[0]
            
            context_blocks = []
            current_chars = 0
            for doc, meta in zip(docs, metadatas):
                source = meta.get("source", "Bilinmeyen Kaynak")
                block = f"--- KAYNAK BELGE ALINTISI [{source}] ---\n{doc}\n--- KAYNAK SONU ---"
                if current_chars + len(block) > max_chars:
                    break
                context_blocks.append(block)
                current_chars += len(block)
                
            return "\n\n".join(context_blocks)
        except Exception as e:
            logger.error(f"RAG arama hatası: {e}")
            return ""


def build_rag_index_from_pdfs(pdf_paths: List[Path], max_chars_per_pdf: Optional[int] = None) -> LocalRAGIndex:
    """
    Reads documents, chunks them, and adds them to ChromaDB.
    """
    rag_index = LocalRAGIndex()
    for path in pdf_paths:
        name = path.name
        try:
            # Read entire document without arbitrary character limits if max_chars is None
            text = read_document(path, max_chars=max_chars_per_pdf)
            rag_index.add_document(name, text)
        except Exception as e:
            logger.warning(f"RAG PDF okunurken hata [{name}]: {e}")
    
    return rag_index
