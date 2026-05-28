import os
import json
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import anthropic
from dotenv import load_dotenv
from rag import WasteRAG

load_dotenv()

app = FastAPI(title="産業廃棄物行政事例検索システム")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

client = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))
rag = WasteRAG()

STATIC_DIR = os.path.join(os.path.dirname(__file__), "..", "frontend")


class Message(BaseModel):
    role: str
    content: str


class QueryRequest(BaseModel):
    message: str
    history: List[Message] = []


class QueryResponse(BaseModel):
    answer: str
    sources: List[dict]
    needs_clarification: bool
    clarification_questions: List[str]


SYSTEM_PROMPT = """あなたは産業廃棄物行政の専門家AIアシスタントです。
長野県を管轄とした産業廃棄物に関する法律・政令・省令・国通知・条例・県通知・判例に基づいて正確に回答します。

【厳守事項】
1. 必ず提供された【参照文書】の内容のみに基づいて回答すること。
2. 参照文書に記載のない事項については「参照文書には記載がありません」と明示すること。
3. 推測・解釈の拡大は一切行わないこと。
4. 回答の根拠となる法令・通知・判例名を必ず明示すること。
5. 質問が曖昧で適切な法令を特定できない場合は、回答の前に確認事項を質問すること。

【回答形式】
- 根拠となる法令条文・通知・判例を【出典】として明記する
- 複数の法令が関連する場合はすべて列挙する
- 「おそらく」「一般的に」などの推測表現を使用しない
- 参照文書に記載がない内容は回答しない

【確認が必要な場合】
以下の場合は回答前に確認事項を提示する：
- 廃棄物の種類が特定できない
- 事業の形態（排出事業者か処理業者か）が不明
- 都道府県・市区町村が特定できず条例の適用が不明
- 質問が複数の法令解釈にまたがり文脈が不明確
"""

CLARIFICATION_CHECK_PROMPT = """以下のユーザーの質問と参照文書を確認し、回答するために追加情報が必要かどうか判断してください。

ユーザーの質問: {question}

参照文書の概要: {doc_summary}

以下のJSON形式のみで回答してください（説明不要）：
{{
  "needs_clarification": true/false,
  "questions": ["確認事項1", "確認事項2"] // needs_clarificationがtrueの場合のみ
}}

判断基準：
- 廃棄物の種類が不明で法令の特定に影響する → 確認必要
- 事業者の立場（排出/収集運搬/処分）が不明で異なる規制が適用される → 確認必要
- 参照文書に関連情報が不十分 → 確認不要（参照文書範囲外として回答）
- 質問が明確で参照文書から回答可能 → 確認不要"""


@app.get("/")
async def root():
    index_path = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {"message": "産業廃棄物行政事例検索システム API稼働中"}


@app.post("/api/query", response_model=QueryResponse)
async def query(request: QueryRequest):
    user_message = request.message.strip()
    if not user_message:
        raise HTTPException(status_code=400, detail="質問を入力してください")

    # 関連法令を検索
    retrieved_docs = rag.search(user_message, n_results=8)

    if not retrieved_docs:
        return QueryResponse(
            answer="申し訳ありませんが、関連する法令文書が見つかりませんでした。",
            sources=[],
            needs_clarification=False,
            clarification_questions=[],
        )

    # 参照文書のテキストを構築
    context_parts = []
    for i, doc in enumerate(retrieved_docs, 1):
        context_parts.append(
            f"[文書{i}] {doc['source_label']}\n{doc['content']}"
        )
    context_text = "\n\n---\n\n".join(context_parts)

    doc_summary = ", ".join(d["source_label"] for d in retrieved_docs[:4])

    # 確認事項チェック（会話履歴がない最初の質問の場合のみ）
    needs_clarification = False
    clarification_questions = []

    if not request.history:
        check_prompt = CLARIFICATION_CHECK_PROMPT.format(
            question=user_message,
            doc_summary=doc_summary,
        )
        check_response = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=512,
            messages=[{"role": "user", "content": check_prompt}],
        )
        try:
            check_text = check_response.content[0].text.strip()
            # JSONのみを抽出
            start = check_text.find("{")
            end = check_text.rfind("}") + 1
            if start >= 0 and end > start:
                check_json = json.loads(check_text[start:end])
                needs_clarification = check_json.get("needs_clarification", False)
                clarification_questions = check_json.get("questions", [])
        except Exception:
            pass

    # 確認が必要な場合はそのまま返す
    if needs_clarification and clarification_questions:
        return QueryResponse(
            answer="",
            sources=[{"label": d["source_label"], "category": d["category"]} for d in retrieved_docs[:4]],
            needs_clarification=True,
            clarification_questions=clarification_questions,
        )

    # 回答生成
    messages = []
    for h in request.history:
        messages.append({"role": h.role, "content": h.content})

    user_content = f"""【参照文書】
{context_text}

【質問】
{user_message}

上記の参照文書のみに基づいて回答してください。参照文書に記載のない内容は「参照文書には記載がありません」と明示してください。"""

    messages.append({"role": "user", "content": user_content})

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=2048,
        system=SYSTEM_PROMPT,
        messages=messages,
    )

    answer = response.content[0].text

    sources = [
        {"label": d["source_label"], "category": d["category"], "relevance": d["relevance"]}
        for d in retrieved_docs
    ]

    return QueryResponse(
        answer=answer,
        sources=sources,
        needs_clarification=False,
        clarification_questions=[],
    )


@app.get("/api/health")
async def health():
    doc_count = len(rag.documents)
    return {"status": "ok", "indexed_documents": doc_count}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
