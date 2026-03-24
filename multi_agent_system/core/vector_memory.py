"""
core/vector_memory.py
ChromaDB-based semantic search for project memory.

Uses sentence-transformers for embeddings and ChromaDB for vector storage.
"""
import os
from pathlib import Path
from typing import List, Dict, Optional
import logging

try:
    import chromadb
    from chromadb.config import Settings
    from sentence_transformers import SentenceTransformer
    CHROMADB_AVAILABLE = True
except ImportError:
    CHROMADB_AVAILABLE = False
    logging.warning("ChromaDB or sentence-transformers not installed. Vector search disabled.")


class VectorMemory:
    """Semantic search for project memory using ChromaDB."""
    
    def __init__(self, db_path: str = None):
        """Initialize ChromaDB client and embedding model."""
        if not CHROMADB_AVAILABLE:
            self.enabled = False
            return
        
        self.enabled = True
        
        # Default path: workspace/chroma_db/
        if db_path is None:
            workspace = Path(__file__).parent.parent / "workspace"
            db_path = str(workspace / "chroma_db")
        
        os.makedirs(db_path, exist_ok=True)
        
        # Initialize ChromaDB client
        self.client = chromadb.PersistentClient(
            path=db_path,
            settings=Settings(
                anonymized_telemetry=False,
                allow_reset=True
            )
        )
        
        # Get or create collection
        self.collection = self.client.get_or_create_collection(
            name="project_memory",
            metadata={"description": "Multi-agent project memory"}
        )
        
        # Load embedding model (lightweight, fast)
        self.model = SentenceTransformer('all-MiniLM-L6-v2')
        
        logging.info(f"[VectorMemory] Initialized with {self.collection.count()} projects")
    
    def add_project(
        self,
        slug: str,
        summary: str,
        code_snippets: List[str] = None,
        metadata: Dict = None
    ) -> bool:
        """
        Add a project to vector database.
        
        Args:
            slug: Project slug (unique ID)
            summary: Project summary text
            code_snippets: List of code snippets (optional)
            metadata: Additional metadata (tags, cost, etc.)
        
        Returns:
            True if successful
        """
        if not self.enabled:
            return False
        
        try:
            # Combine summary and code snippets for embedding
            text_parts = [summary]
            if code_snippets:
                text_parts.extend(code_snippets[:5])  # Max 5 snippets
            
            combined_text = "\n\n".join(text_parts)
            
            # Generate embedding
            embedding = self.model.encode(combined_text).tolist()
            
            # Prepare metadata
            meta = metadata or {}
            meta["slug"] = slug
            meta["summary_length"] = len(summary)
            
            # ChromaDB upsert yaparken lists/None boş olmamalı
            tags = meta.get("tags")
            if not tags:
                meta["tags"] = ["general"]
            
            # Add to collection (upsert if exists)
            self.collection.upsert(
                ids=[slug],
                embeddings=[embedding],
                documents=[combined_text],
                metadatas=[meta]
            )
            
            logging.info(f"[VectorMemory] Added project: {slug}")
            return True
            
        except Exception as e:
            logging.error(f"[VectorMemory] Error adding project {slug}: {e}")
            return False
    
    def search_similar(
        self,
        query: str,
        n: int = 3,
        min_similarity: float = 0.3
    ) -> List[Dict]:
        """
        Search for semantically similar projects.
        
        Args:
            query: Search query (user goal or description)
            n: Number of results to return
            min_similarity: Minimum similarity threshold (0-1)
        
        Returns:
            List of dicts with keys: slug, summary, similarity, metadata
        """
        if not self.enabled or self.collection.count() == 0:
            return []
        
        try:
            # Generate query embedding
            query_embedding = self.model.encode(query).tolist()
            
            # Search in ChromaDB
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=min(n, self.collection.count())
            )
            
            # Parse results
            projects = []
            if results['ids'] and results['ids'][0]:
                for i, slug in enumerate(results['ids'][0]):
                    # ChromaDB returns distance, convert to similarity
                    distance = results['distances'][0][i]
                    similarity = 1.0 / (1.0 + distance)  # Convert distance to similarity
                    
                    if similarity >= min_similarity:
                        meta = results['metadatas'][0][i]
                        
                        # AKTİF ÖĞRENME AĞIRLIĞI HESAPLAMA (Başarıyı ödüllendir, maliyeti cezalandır)
                        cost = float(meta.get("cost", 0.0))
                        success_rate = float(meta.get("success_rate", 1.0))
                        
                        score = similarity * (1.0 + success_rate)
                        if cost > 0:
                            score = score / (1.0 + (cost * 5))  # Maliyet çarpanı
                            
                        # Belgenin tamamını alalım (veya daha fazlasını kestirip dönelim)
                        doc_content = results['documents'][0][i] if results.get('documents') and results['documents'][0] else ""
                        doc_summary = doc_content if len(doc_content) < 1500 else doc_content[:1500] + "..."
                            
                        projects.append({
                            "slug": slug,
                            "summary": doc_summary,
                            "similarity": round(similarity, 3),
                            "score": round(score, 3),
                            "metadata": meta
                        })
            
            # Active Learning Skoru'na göre sırala
            projects.sort(key=lambda x: x["score"], reverse=True)
            
            logging.info(f"[VectorMemory] Found {len(projects)} similar projects for query")
            return projects
            
        except Exception as e:
            logging.error(f"[VectorMemory] Search error: {e}")
            return []
    
    def get_context(self, query: str, max_length: int = 2000) -> str:
        """
        Get formatted context string for Coder agent.
        
        Args:
            query: User goal or task description
            max_length: Maximum context length in characters
        
        Returns:
            Formatted context string with similar projects
        """
        if not self.enabled:
            return ""
        
        similar = self.search_similar(query, n=3)
        
        if not similar:
            return ""
        
        context_parts = ["📚 Similar Projects (Semantic Search):"]
        
        for proj in similar:
            tags = proj['metadata'].get('tags', [])
            tags_str = ", ".join(tags) if tags else "none"
            
            context_parts.append(
                f"\n• {proj['slug']} (similarity: {proj['similarity']})\n"
                f"  Tags: {tags_str}\n"
                f"  Summary: {proj['summary'][:200]}..."
            )
        
        context = "\n".join(context_parts)
        
        # Truncate if too long
        if len(context) > max_length:
            context = context[:max_length] + "\n... (truncated)"
        
        return context
    
    def delete_project(self, slug: str) -> bool:
        """Delete a project from vector database."""
        if not self.enabled:
            return False
        
        try:
            self.collection.delete(ids=[slug])
            logging.info(f"[VectorMemory] Deleted project: {slug}")
            return True
        except Exception as e:
            logging.error(f"[VectorMemory] Delete error: {e}")
            return False
    
    def count(self) -> int:
        """Get total number of projects in vector database."""
        if not self.enabled:
            return 0
        return self.collection.count()
    
    def reset(self):
        """Clear all projects from vector database."""
        if not self.enabled:
            return
        
        try:
            self.client.delete_collection("project_memory")
            self.collection = self.client.create_collection("project_memory")
            logging.info("[VectorMemory] Database reset")
        except Exception as e:
            logging.error(f"[VectorMemory] Reset error: {e}")


# Singleton instance
_vector_memory = None

def get_vector_memory() -> VectorMemory:
    """Get or create singleton VectorMemory instance."""
    global _vector_memory
    if _vector_memory is None:
        _vector_memory = VectorMemory()
    return _vector_memory
