import os
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np
from typing import List, Dict, Any
from document_loader import load_all_documents, format_source_label

DOCS_DIR = os.path.join(os.path.dirname(__file__), "legal_docs")


class WasteRAG:
    def __init__(self):
        self.documents: List[Dict[str, Any]] = []
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(2, 4),
            min_df=1,
            sublinear_tf=True,
        )
        self._build_index()

    def _build_index(self):
        """法令文書をTF-IDFでインデックス化"""
        raw_docs = load_all_documents(DOCS_DIR)
        if not raw_docs:
            return

        self.documents = raw_docs
        texts = [d["full_text"] for d in raw_docs]
        self.tfidf_matrix = self.vectorizer.fit_transform(texts)

    def search(self, query: str, n_results: int = 8) -> List[Dict[str, Any]]:
        """クエリに関連する法令文書をTF-IDF類似度で取得"""
        if not self.documents:
            return []

        q_vec = self.vectorizer.transform([query])
        scores = cosine_similarity(q_vec, self.tfidf_matrix)[0]
        top_indices = np.argsort(scores)[::-1][:n_results]

        results = []
        for idx in top_indices:
            if scores[idx] < 0.01:
                continue
            doc = self.documents[idx]
            results.append(
                {
                    "id": doc["id"],
                    "source_label": format_source_label(doc),
                    "content": doc["content"],
                    "category": doc["category"],
                    "relevance": round(float(scores[idx]), 3),
                }
            )

        return results

    def rebuild_index(self):
        self._build_index()
