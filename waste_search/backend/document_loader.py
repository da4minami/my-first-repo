import os
import yaml
import glob
from typing import List, Dict, Any


def load_all_documents(docs_dir: str) -> List[Dict[str, Any]]:
    """法令ディレクトリ配下のYAMLファイルをすべて読み込む"""
    documents = []
    yaml_files = glob.glob(os.path.join(docs_dir, "**", "*.yaml"), recursive=True)

    for file_path in yaml_files:
        with open(file_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        category = data.get("category", "不明")
        title = data.get("title", "")
        law_number = data.get("law_number", "")
        prefecture = data.get("prefecture", "")

        for section in data.get("sections", []):
            doc = {
                "id": section.get("id", ""),
                "source_file": os.path.basename(file_path),
                "category": category,
                "law_title": title,
                "law_number": law_number,
                "prefecture": prefecture,
                "article": section.get("article", ""),
                "section_title": section.get("section_title") or section.get("title", ""),
                "content": section.get("content", ""),
                "keywords": section.get("keywords", []),
                "court": section.get("court", ""),
                "date": section.get("date", ""),
                "case_number": section.get("case_number", ""),
                "issued_by": section.get("issued_by", ""),
                "issued_date": section.get("issued_date", ""),
            }
            # フルテキスト（検索・埋め込み用）
            parts = [
                f"【{category}】{title}",
                f"{doc['article']} {doc['section_title']}",
                doc["content"],
                " ".join(doc["keywords"]),
            ]
            if law_number:
                parts.insert(1, law_number)
            if prefecture:
                parts.insert(1, prefecture)
            doc["full_text"] = "\n".join(p for p in parts if p.strip())
            documents.append(doc)

    return documents


def format_source_label(doc: Dict[str, Any]) -> str:
    """参照元の表示ラベルを生成"""
    parts = [f"【{doc['category']}】"]
    if doc.get("prefecture"):
        parts.append(doc["prefecture"])
    parts.append(doc["law_title"])
    if doc.get("article"):
        parts.append(doc["article"])
    if doc.get("section_title"):
        parts.append(doc["section_title"])
    if doc.get("court"):
        parts.append(f"{doc['court']} {doc.get('date', '')}")
    return " ".join(parts)
