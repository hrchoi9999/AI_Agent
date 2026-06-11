from __future__ import annotations

import base64
import hashlib
import html
import io
import json
import os
import re
import threading
import urllib.request
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlparse

import streamlit as st
import streamlit.components.v1 as components
from dotenv import load_dotenv
from google import genai
from google.genai import types as genai_types
from langchain_community.document_loaders import PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from openai import OpenAI
from PIL import Image
from youtube_transcript_api import YouTubeTranscriptApi


MIN_CHUNK_CHARS = 80
CHUNK_SIZE = 900
CHUNK_OVERLAP = 120
MAX_EMBED_TEXT_CHARS = 6_000
MAX_YOUTUBE_SUMMARY_CHARS = 20_000
MAX_INFOGRAPHIC_TEXT_CHARS = 16_000
EMBEDDING_MODEL = "text-embedding-3-small"
ANSWER_MODEL = "gpt-4.1-mini"
GEMINI_VIDEO_MODEL = "gemini-2.5-flash"
GEMINI_IMAGE_MODEL = "gemini-2.5-flash-image"
YOUTUBE_RESULT_VERSION = "2026-06-10-multi-youtube-qa"
INFOGRAPHIC_PROMPT_VERSION = "2026-06-10-light-template-v3"
INFOGRAPHIC_REQUEST_LIMIT = 15
INFOGRAPHIC_PROMPT_FILE = Path(os.getenv("INFOGRAPHIC_PROMPT_FILE", "infographic_prompts.local.json"))
INFOGRAPHIC_USAGE_FILE = Path(os.getenv("INFOGRAPHIC_USAGE_FILE", "infographic_usage.local.json"))
INFOGRAPHIC_USAGE_LOCK = threading.Lock()


@dataclass(frozen=True)
class PdfChunk:
    source_name: str
    page_number: int
    chunk_number: int
    text: str


@dataclass(frozen=True)
class InfographicTemplate:
    index: int
    title: str
    prompt: str
    image_url: str


INFOGRAPHIC_TEMPLATES: tuple[InfographicTemplate, ...] = (
    InfographicTemplate(
        1,
        "화이트 플로우 카드 스타일",
        "Bright white flow-card infographic, pure white background, light sky-blue cards, navy text, soft shadows, clean vector icons, simple arrows, polished presentation summary --ar 16:9",
        "https://jiooi.notion.site/image/attachment%3Acd29a08f-5c71-4815-a2f8-00ef720f9d1e%3A5_%EB%89%B4%EB%AA%A8%ED%94%BC%EC%A6%98_%EC%8A%A4%ED%83%80%EC%9D%BC_(%EB%AA%A8%EB%8D%98_%EC%9B%B9%EC%82%AC%EC%9D%B4%ED%8A%B8)_1.png?table=block&id=3647603d-5e70-8123-982d-c469b79d6f48&spaceId=0fbe4b84-4932-4da1-a7a6-368d103af509&width=640&userId=&cache=v2&imgBuildSrc=requestProxiedImageUrl",
    ),
    InfographicTemplate(
        2,
        "비즈니스 미니멀 스타일",
        "Minimalist timeline infographic, simple flat vector art, clean data visualization, geometric shapes, corporate color palette, white background, highly legible --ar 16:9",
        "https://jiooi.notion.site/image/attachment%3A04398c7b-2021-4414-8e79-49adc2aebe3f%3A2_%EB%B9%84%EC%A6%88%EB%8B%88%EC%8A%A4_%EB%AF%B8%EB%8B%88%EB%A9%80_%EC%8A%A4%ED%83%80%EC%9D%BC_2.png?table=block&id=3647603d-5e70-81f4-b8c8-df09b8bd3b5a&spaceId=0fbe4b84-4932-4da1-a7a6-368d103af509&width=640&userId=&cache=v2&imgBuildSrc=requestProxiedImageUrl",
    ),
    InfographicTemplate(
        3,
        "밝은 교육 슬라이드 스타일",
        "Bright educational slide infographic, warm white background, pale yellow and sky blue panels, friendly icons, clean arrows, modern presentation style, no chalkboard, no dark green board, no blackboard --ar 16:9",
        "data:image/svg+xml,%3Csvg%20xmlns='http://www.w3.org/2000/svg'%20viewBox='0%200%20640%20360'%3E%3Crect%20width='640'%20height='360'%20rx='28'%20fill='%23fffaf0'/%3E%3Crect%20x='58'%20y='62'%20width='524'%20height='74'%20rx='22'%20fill='%23e0f2fe'/%3E%3Ctext%20x='320'%20y='108'%20text-anchor='middle'%20font-family='Arial'%20font-size='30'%20font-weight='800'%20fill='%231e3a8a'%3E%EA%B5%90%EC%9C%A1%20%EC%8A%AC%EB%9D%BC%EC%9D%B4%EB%93%9C%20%EC%9A%94%EC%95%BD%3C/text%3E%3Cg%20font-family='Arial'%20font-size='18'%20font-weight='700'%20fill='%23334155'%3E%3Crect%20x='70'%20y='176'%20width='140'%20height='96'%20rx='18'%20fill='%23fef3c7'/%3E%3Ctext%20x='140'%20y='230'%20text-anchor='middle'%3EStep%201%3C/text%3E%3Crect%20x='250'%20y='176'%20width='140'%20height='96'%20rx='18'%20fill='%23dcfce7'/%3E%3Ctext%20x='320'%20y='230'%20text-anchor='middle'%3EStep%202%3C/text%3E%3Crect%20x='430'%20y='176'%20width='140'%20height='96'%20rx='18'%20fill='%23fee2e2'/%3E%3Ctext%20x='500'%20y='230'%20text-anchor='middle'%3EStep%203%3C/text%3E%3C/g%3E%3C/svg%3E",
    ),
    InfographicTemplate(
        4,
        "파스텔 에디토리얼 스타일",
        "Bright pastel editorial magazine infographic, ivory background, soft pastel blue green pink accents, elegant section cards, refined whitespace, clean line icons --ar 16:9",
        "https://jiooi.notion.site/image/attachment%3Ac03ad15c-2c19-4bc3-abe0-c13d04367626%3A6_%EB%B0%94%EC%9A%B0%ED%95%98%EC%9A%B0%EC%8A%A4_(%ED%98%84%EB%8C%80_%EA%B1%B4%EC%B6%95%ED%98%84%EB%8C%80_%EB%AF%B8%EC%88%A0)_%EC%8A%A4%ED%83%80%EC%9D%BC_1.png?table=block&id=3647603d-5e70-818e-a671-d1418f6e4c62&spaceId=0fbe4b84-4932-4da1-a7a6-368d103af509&width=640&userId=&cache=v2&imgBuildSrc=requestProxiedImageUrl",
    ),
    InfographicTemplate(
        5,
        "라이트 아이소메트릭 스타일",
        "Bright isometric vector infographic, white and light gray background, soft blue and mint accents, clean isometric icons, airy layout, modern data summary --ar 16:9",
        "https://jiooi.notion.site/image/attachment%3A7d50c2b2-f245-4d32-ad46-76eb7bcd4b5c%3A10_%ED%81%B4%EB%A0%88%EC%9D%B4_%EC%95%A0%EB%8B%88%EB%A9%94%EC%9D%B4%EC%85%98_%EC%8A%A4%ED%83%80%EC%9D%BC_1.png?table=block&id=3647603d-5e70-8183-849c-e664e267d2da&spaceId=0fbe4b84-4932-4da1-a7a6-368d103af509&width=640&userId=&cache=v2&imgBuildSrc=requestProxiedImageUrl",
    ),
)


def normalize_text(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    return [token.lower() for token in re.findall(r"[A-Za-z0-9가-힣]{2,}", text)]


@st.cache_data(show_spinner=False)
def extract_pages_from_pdf(pdf_bytes: bytes) -> list[tuple[int, str]]:
    temp_path: str | None = None
    try:
        with NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
            temp_file.write(pdf_bytes)
            temp_path = temp_file.name
        documents = PyPDFLoader(temp_path).load()
    finally:
        if temp_path:
            Path(temp_path).unlink(missing_ok=True)

    pages: list[tuple[int, str]] = []
    for index, document in enumerate(documents, start=1):
        page_number = int(document.metadata.get("page", index - 1)) + 1
        text = normalize_text(document.page_content or "")
        if text:
            pages.append((page_number, text))
    return pages


@st.cache_data(show_spinner=False)
def build_chunks(pages: list[tuple[str, int, str]]) -> list[PdfChunk]:
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=["\n\n", "\n", ". ", "? ", " ", ""],
    )
    chunks: list[PdfChunk] = []
    chunk_number = 1
    for source_name, page_number, page_text in pages:
        for chunk_text in splitter.split_text(page_text):
            chunk_text = normalize_text(chunk_text)
            if len(chunk_text) >= MIN_CHUNK_CHARS:
                chunks.append(PdfChunk(source_name, page_number, chunk_number, chunk_text))
                chunk_number += 1
    return chunks


@st.cache_data(show_spinner=False)
def embed_texts(texts: tuple[str, ...], model: str) -> list[list[float]]:
    client = OpenAI()
    response = client.embeddings.create(model=model, input=list(texts))
    return [item.embedding for item in response.data]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    numerator = sum(a * b for a, b in zip(left, right))
    left_norm = sum(a * a for a in left) ** 0.5
    right_norm = sum(b * b for b in right) ** 0.5
    if not left_norm or not right_norm:
        return 0.0
    return numerator / (left_norm * right_norm)


def find_relevant_chunks(question: str, chunks: list[PdfChunk], limit: int = 8) -> list[tuple[PdfChunk, float]]:
    terms = tokenize(question)
    if not terms:
        return []
    ranked: list[tuple[PdfChunk, float]] = []
    for chunk in chunks:
        lowered = chunk.text.lower()
        score = sum(lowered.count(term) for term in terms)
        if score:
            ranked.append((chunk, float(score)))
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:limit]


def find_semantic_chunks(question: str, chunks: list[PdfChunk], limit: int = 8) -> list[tuple[PdfChunk, float]]:
    if not chunks:
        return []
    query_embedding = embed_texts((question,), EMBEDDING_MODEL)[0]
    chunk_texts = tuple(chunk.text[:MAX_EMBED_TEXT_CHARS] for chunk in chunks)
    chunk_embeddings = embed_texts(chunk_texts, EMBEDDING_MODEL)
    ranked = [
        (chunk, cosine_similarity(query_embedding, embedding))
        for chunk, embedding in zip(chunks, chunk_embeddings)
    ]
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:limit]


def is_page_location_question(question: str) -> bool:
    lowered = question.lower()
    return any(hint in lowered for hint in ("몇페이지", "몇 페이지", "페이지", "page", "어디", "위치"))


def find_page_location_chunks(question: str, chunks: list[PdfChunk], limit: int) -> list[tuple[PdfChunk, float]]:
    terms = tokenize(question)
    best_by_page: dict[tuple[str, int], tuple[PdfChunk, float]] = {}
    for chunk in chunks:
        lowered = chunk.text.lower()
        matched = [term for term in terms if term in lowered]
        if not matched:
            continue
        score = sum(lowered.count(term) for term in matched) + len(set(matched)) * 10
        key = (chunk.source_name, chunk.page_number)
        if key not in best_by_page or score > best_by_page[key][1]:
            best_by_page[key] = (chunk, float(score))
    ranked = list(best_by_page.values())
    ranked.sort(key=lambda item: item[1], reverse=True)
    return ranked[:limit]


@st.cache_data(show_spinner=False)
def generate_answer(question: str, context_items: tuple[tuple[str, int, str], ...], model: str) -> str:
    context = "\n\n".join(
        f"[{source_name} / Page {page_number}]\n{text[:1_500]}"
        for source_name, page_number, text in context_items[:8]
    )
    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": (
                    "PDF에서 추출한 텍스트만 근거로 한국어로 답하세요. "
                    "근거에 없는 내용은 추측하지 마세요. "
                    "핵심 인명, 작품명, 회사명, 개념은 **굵게** 표시하세요."
                ),
            },
            {"role": "user", "content": f"질문: {question}\n\nPDF 근거:\n{context}"},
        ],
        temperature=0.2,
    )
    return (response.choices[0].message.content or "").strip()


def parse_youtube_urls(raw_text: str) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    for value in re.split(r"[\s,]+", raw_text.strip()):
        url = value.strip()
        if not url:
            continue
        if not url.startswith(("http://", "https://")):
            url = f"https://{url}"
        if extract_youtube_video_id(url) and url not in seen:
            urls.append(url)
            seen.add(url)
    return urls


def extract_youtube_video_id(url: str) -> str | None:
    parsed = urlparse(url.strip())
    host = parsed.netloc.lower()
    if host.endswith("youtu.be"):
        return parsed.path.strip("/") or None
    if "youtube.com" in host:
        if parsed.path == "/watch":
            return parse_qs(parsed.query).get("v", [None])[0]
        if parsed.path.startswith("/shorts/") or parsed.path.startswith("/embed/"):
            parts = parsed.path.split("/")
            return parts[2] if len(parts) > 2 else None
    return None


@st.cache_data(show_spinner=False)
def fetch_youtube_title(video_url: str, video_id: str) -> str:
    try:
        oembed_url = "https://www.youtube.com/oembed?format=json&url=" + video_url
        with urllib.request.urlopen(oembed_url, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return normalize_text(str(payload.get("title", ""))) or f"YouTube {video_id}"
    except Exception:
        return f"YouTube {video_id}"


@st.cache_data(show_spinner=False)
def fetch_youtube_transcript(video_id: str) -> str:
    transcript = YouTubeTranscriptApi().fetch(video_id, languages=("ko", "en"))
    lines: list[str] = []
    for item in transcript:
        text = getattr(item, "text", None)
        if text is None and isinstance(item, dict):
            text = item.get("text")
        if text:
            lines.append(normalize_text(text))
    return "\n".join(lines).strip()


@st.cache_data(show_spinner=False)
def generate_youtube_summary(video_url: str, transcript_text: str, model: str) -> str:
    source_text = transcript_text[:MAX_YOUTUBE_SUMMARY_CHARS]
    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "유튜브 자막만 근거로 한국어 요약을 작성하세요. 핵심 주제, 주요 내용, 실천/학습 포인트를 간결하게 정리하세요.",
            },
            {"role": "user", "content": f"영상 URL: {video_url}\n\n자막:\n{source_text}"},
        ],
        temperature=0.2,
    )
    return (response.choices[0].message.content or "").strip()


@st.cache_data(show_spinner=False)
def generate_gemini_youtube_summary(video_url: str, model: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않습니다.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=genai_types.Content(
            parts=[
                genai_types.Part(file_data=genai_types.FileData(file_uri=video_url)),
                genai_types.Part(text="이 유튜브 영상을 한국어로 요약해 주세요. 확인되지 않는 내용은 추측하지 마세요."),
            ]
        ),
    )
    return (response.text or "").strip()


@st.cache_data(show_spinner=False)
def generate_youtube_answer(question: str, context_items: tuple[tuple[str, str], ...], model: str) -> str:
    context = "\n\n".join(f"[{title}]\n{text[:2_000]}" for title, text in context_items[:8])
    client = OpenAI()
    response = client.chat.completions.create(
        model=model,
        messages=[
            {
                "role": "system",
                "content": "유튜브 영상 요약문만 근거로 한국어로 답하세요. 요약문에 없는 내용은 추측하지 마세요. 핵심 단어는 **굵게** 표시하세요.",
            },
            {"role": "user", "content": f"질문: {question}\n\n유튜브 요약 근거:\n{context}"},
        ],
        temperature=0.2,
    )
    return (response.choices[0].message.content or "").strip()


def read_infographic_usage() -> dict[str, object]:
    if not INFOGRAPHIC_USAGE_FILE.exists():
        return {"count": 0, "limit": INFOGRAPHIC_REQUEST_LIMIT, "started_at": ""}
    try:
        usage = json.loads(INFOGRAPHIC_USAGE_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"count": 0, "limit": INFOGRAPHIC_REQUEST_LIMIT, "started_at": ""}
    return {
        "count": max(0, int(usage.get("count", 0))),
        "limit": INFOGRAPHIC_REQUEST_LIMIT,
        "started_at": str(usage.get("started_at", "")),
    }


def reserve_infographic_request() -> bool:
    with INFOGRAPHIC_USAGE_LOCK:
        usage = read_infographic_usage()
        count = int(usage["count"])
        if count >= INFOGRAPHIC_REQUEST_LIMIT:
            return False
        usage["count"] = count + 1
        usage["limit"] = INFOGRAPHIC_REQUEST_LIMIT
        usage["started_at"] = usage["started_at"] or datetime.now().isoformat(timespec="seconds")
        INFOGRAPHIC_USAGE_FILE.write_text(json.dumps(usage, ensure_ascii=False, indent=2), encoding="utf-8")
        return True


@st.cache_data(show_spinner=False)
def load_infographic_prompt_specs(prompt_file: str) -> dict[str, str]:
    path = Path(prompt_file)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    specs: dict[str, str] = {}
    for key, value in raw.items():
        if isinstance(value, str):
            specs[str(key)] = value.strip()
        elif isinstance(value, dict):
            prompt = value.get("image_prompt") or value.get("prompt")
            if isinstance(prompt, str):
                specs[str(key)] = prompt.strip()
    return specs


def get_infographic_prompt_spec(template: InfographicTemplate) -> str:
    return load_infographic_prompt_specs(str(INFOGRAPHIC_PROMPT_FILE)).get(str(template.index), template.prompt)


def first_text(value: object, fallback: str = "") -> str:
    return normalize_text(value) if isinstance(value, str) else fallback


def list_text(value: object, limit: int, fallback: list[str]) -> list[str]:
    if isinstance(value, list):
        items = [normalize_text(str(item)) for item in value if normalize_text(str(item))]
    elif isinstance(value, str):
        items = [normalize_text(line.strip("- 1234567890. ")) for line in value.splitlines()]
        items = [item for item in items if item]
    else:
        items = []
    return (items or fallback)[:limit]


def clean_infographic_copy(text: object, max_chars: int) -> str:
    cleaned = normalize_text(str(text or "")).replace("\u200b", "")
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()[:max_chars]


def normalize_infographic_brief(brief: dict[str, object]) -> dict[str, object]:
    return {
        "title": clean_infographic_copy(brief.get("title"), 24),
        "subtitle": clean_infographic_copy(brief.get("subtitle"), 42),
        "key_points": [clean_infographic_copy(item, 34) for item in list_text(brief.get("key_points"), 4, [])],
        "flow": [clean_infographic_copy(item, 24) for item in list_text(brief.get("flow"), 3, [])],
        "keywords": [clean_infographic_copy(item, 16) for item in list_text(brief.get("keywords"), 5, [])],
        "takeaway": clean_infographic_copy(brief.get("takeaway"), 54),
    }


@st.cache_data(show_spinner=False)
def generate_infographic_brief(
    source_type: str,
    source_title: str,
    source_text: str,
    template_title: str,
    template_prompt: str,
    model: str,
) -> dict[str, object]:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않습니다.")
    client = genai.Client(api_key=api_key)
    prompt = (
        "문서나 영상의 추출 텍스트만 근거로 한국어 인포그래픽 내용을 JSON으로 만드세요.\n"
        "title, subtitle, key_points(4개), flow(3개), keywords(5개), takeaway 필드를 반환하세요.\n"
        f"자료 유형: {source_type}\n자료명: {source_title}\n템플릿: {template_title}\n템플릿 지시: {template_prompt}\n\n"
        f"자료 텍스트:\n{source_text[:MAX_INFOGRAPHIC_TEXT_CHARS]}"
    )
    response = client.models.generate_content(
        model=model,
        contents=prompt,
        config=genai_types.GenerateContentConfig(response_mime_type="application/json"),
    )
    return normalize_infographic_brief(json.loads(response.text or "{}"))


def ensure_png_bytes(image_bytes: bytes) -> bytes:
    if image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        return image_bytes
    with Image.open(io.BytesIO(image_bytes)) as image:
        output = io.BytesIO()
        image.convert("RGB").save(output, format="PNG")
        return output.getvalue()


def build_infographic_image_prompt(brief: dict[str, object], template_title: str, template_prompt: str, source_title: str) -> str:
    key_points = list_text(brief.get("key_points"), 4, [])
    return (
        "Create a premium 16:9 Korean infographic image.\n"
        f"Visual template style to follow strongly: {template_title} / {template_prompt}\n"
        "Quality rules: clean composition, strong hierarchy, no clutter, no overlapping text, large readable Korean text.\n"
        "TEXT ACCURACY RULES: render the Korean copy exactly as provided below. Do not invent fake Korean.\n\n"
        f"Source: {source_title}\n"
        f"- Title: {brief['title']}\n"
        f"- Subtitle: {brief['subtitle']}\n"
        + "\n".join(f"- Key point {i + 1}: {text}" for i, text in enumerate(key_points))
        + f"\n- Flow: {' > '.join(list_text(brief.get('flow'), 3, []))}\n"
        f"- Keywords: {', '.join(list_text(brief.get('keywords'), 5, []))}\n"
        f"- Takeaway: {brief['takeaway']}\n"
    )


@st.cache_data(show_spinner=False)
def generate_gemini_infographic_image(
    brief: dict[str, object],
    template_title: str,
    template_prompt: str,
    source_title: str,
    request_signature: str,
    model: str,
) -> bytes:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY가 설정되어 있지 않습니다.")
    _ = request_signature
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(
        model=model,
        contents=build_infographic_image_prompt(brief, template_title, template_prompt, source_title),
        config=genai_types.GenerateContentConfig(
            response_modalities=["IMAGE"],
            image_config=genai_types.ImageConfig(aspect_ratio="16:9"),
        ),
    )
    for candidate in response.candidates or []:
        if not candidate.content:
            continue
        for part in candidate.content.parts or []:
            inline_data = getattr(part, "inline_data", None)
            if inline_data and inline_data.data:
                data = inline_data.data
                if isinstance(data, str):
                    data = base64.b64decode(data)
                return ensure_png_bytes(data)
    raise RuntimeError("Gemini가 이미지 데이터를 반환하지 않았습니다.")


def build_infographic_signature(template: InfographicTemplate, prompt_spec: str, source_title: str, source_text: str) -> str:
    payload = {
        "prompt_version": INFOGRAPHIC_PROMPT_VERSION,
        "image_model": os.getenv("GEMINI_IMAGE_MODEL", GEMINI_IMAGE_MODEL),
        "template_index": template.index,
        "template_title": template.title,
        "prompt_spec": prompt_spec,
        "source_title": source_title,
        "source_hash": hashlib.sha256(source_text.encode("utf-8")).hexdigest(),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def source_text_from_pages(pages: list[tuple[str, int, str]]) -> str:
    return "\n\n".join(f"[{source_name} / Page {page_number}]\n{text}" for source_name, page_number, text in pages)


def safe_download_name(source_title: str, template: InfographicTemplate) -> str:
    raw_name = f"{Path(source_title).stem or 'summary'}-{template.index:02d}-infographic.png"
    return re.sub(r"[^A-Za-z0-9가-힣_-]+", "_", raw_name)


def format_page_refs(page_numbers: list[int]) -> str:
    return ", ".join(f"Page {page_number}" for page_number in page_numbers) if page_numbers else "근거 페이지 없음"


def format_chunk_refs(chunks: list[PdfChunk]) -> str:
    if not chunks:
        return "근거 없음"
    return ", ".join(
        f"{chunk.source_name} · Page {chunk.page_number} · Chunk {chunk.chunk_number}"
        for chunk in chunks
    )


def render_answer_html(answer: str) -> str:
    escaped = html.escape(answer)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    return escaped.replace("\n", "<br>")


def render_copy_button(text: str, key: str) -> None:
    payload = json.dumps(text, ensure_ascii=False)
    components.html(
        f"""
        <button id="copy-{key}" title="복사하기" style="
            width:34px;height:34px;border:1px solid #ececef;border-radius:8px;
            background:#fff;display:inline-flex;align-items:center;justify-content:center;
            cursor:pointer;color:#4b5563;">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor"
               stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <rect x="8" y="8" width="12" height="12" rx="2"></rect>
            <path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path>
          </svg>
        </button>
        <script>
        const button = document.getElementById("copy-{key}");
        button.addEventListener("click", async () => {{
            await navigator.clipboard.writeText({payload});
            button.style.borderColor = "#e03030";
            setTimeout(() => button.style.borderColor = "#ececef", 900);
        }});
        </script>
        """,
        height=42,
    )


def render_pdf_pages(pages: list[tuple[str, int, str]]) -> None:
    st.markdown('<div class="result-title">PDF에서 추출한 전체 텍스트</div>', unsafe_allow_html=True)
    grouped_pages: dict[str, list[tuple[int, str]]] = {}
    for source_name, page_number, page_text in pages:
        grouped_pages.setdefault(source_name, []).append((page_number, page_text))
    tabs = st.tabs(list(grouped_pages.keys()))
    for tab, (source_name, document_pages) in zip(tabs, grouped_pages.items()):
        with tab:
            st.caption(f"{source_name} · {len(document_pages)}페이지")
            for page_number, page_text in document_pages:
                with st.expander(f"Page {page_number}", expanded=page_number == 1):
                    key_seed = hashlib.sha256((source_name + str(page_number)).encode("utf-8")).hexdigest()[:12]
                    st.text_area("페이지 텍스트", page_text, height=260, label_visibility="collapsed", key=f"pdf_page_text_{key_seed}")


def highlight_terms(text: str, question: str) -> str:
    escaped_text = html.escape(text)
    for term in sorted(set(tokenize(question)), key=len, reverse=True)[:8]:
        escaped_text = re.sub(f"({re.escape(html.escape(term))})", r"<mark>\1</mark>", escaped_text, flags=re.IGNORECASE)
    return escaped_text


def select_infographic_template(key_prefix: str, template_index: int) -> None:
    selected_key = f"{key_prefix}_infographic_template"
    st.session_state[selected_key] = template_index
    for suffix in ("infographic_png", "infographic_meta", "infographic_brief"):
        st.session_state.pop(f"{key_prefix}_{suffix}", None)
    for template in INFOGRAPHIC_TEMPLATES:
        st.session_state[f"{key_prefix}_template_checked_{template.index}"] = template.index == template_index


def render_infographic_section(source_type: str, source_title: str, source_text: str, key_prefix: str) -> None:
    st.markdown('<div class="result-title">인포그래픽 요약</div>', unsafe_allow_html=True)
    if not source_text.strip():
        st.info("인포그래픽을 만들 추출 텍스트가 없습니다.")
        return

    selected_key = f"{key_prefix}_infographic_template"
    png_key = f"{key_prefix}_infographic_png"
    meta_key = f"{key_prefix}_infographic_meta"
    brief_key = f"{key_prefix}_infographic_brief"
    if selected_key not in st.session_state:
        st.session_state[selected_key] = INFOGRAPHIC_TEMPLATES[0].index

    columns = st.columns(5, gap="small")
    for column, template in zip(columns, INFOGRAPHIC_TEMPLATES):
        with column:
            border = "#ba1f24" if st.session_state[selected_key] == template.index else "#f1d4d5"
            st.markdown(f'<div class="template-title-text">{html.escape(template.title)}</div>', unsafe_allow_html=True)
            st.checkbox(
                "선택",
                key=f"{key_prefix}_template_checked_{template.index}",
                on_change=select_infographic_template,
                args=(key_prefix, template.index),
                label_visibility="collapsed",
            )
            st.markdown(
                f'<img src="{html.escape(template.image_url, quote=True)}" class="template-thumb" style="border-color:{border};" />',
                unsafe_allow_html=True,
            )

    selected_template = next(t for t in INFOGRAPHIC_TEMPLATES if t.index == st.session_state[selected_key])
    prompt_spec = get_infographic_prompt_spec(selected_template)
    signature = build_infographic_signature(selected_template, prompt_spec, source_title, source_text)
    if st.session_state.get(meta_key, {}).get("signature") != signature:
        st.session_state.pop(png_key, None)
        st.session_state.pop(meta_key, None)
        st.session_state.pop(brief_key, None)

    st.markdown(f'<div class="result-meta">선택 템플릿: {html.escape(selected_template.title)}</div>', unsafe_allow_html=True)
    _, button_center, _ = st.columns([1, 1.25, 1])
    with button_center:
        make_infographic = st.button("인포그래픽 만들기", type="primary", key=f"{key_prefix}_make_infographic", use_container_width=True)

    if make_infographic:
        if not reserve_infographic_request():
            st.error("재료가 떨어져서 인포그래픽을 만들 수 없습니다.")
            return
        working = st.empty()
        working.markdown('<div class="working-line"><span class="working-icon"></span> 인포그래픽을 생성중입니다</div>', unsafe_allow_html=True)
        try:
            brief = generate_infographic_brief(
                source_type,
                source_title,
                source_text,
                selected_template.title,
                prompt_spec,
                os.getenv("GEMINI_TEXT_MODEL", GEMINI_VIDEO_MODEL),
            )
            st.session_state[brief_key] = brief
            st.session_state[png_key] = generate_gemini_infographic_image(
                brief,
                selected_template.title,
                prompt_spec,
                source_title,
                signature,
                os.getenv("GEMINI_IMAGE_MODEL", GEMINI_IMAGE_MODEL),
            )
            st.session_state[meta_key] = {
                "source_title": source_title,
                "signature": signature,
                "template_index": selected_template.index,
                "template_title": selected_template.title,
                "file_name": safe_download_name(source_title, selected_template),
            }
        except Exception as exc:
            st.error(f"인포그래픽 생성에 실패했습니다: {exc}")
        finally:
            working.empty()

    if brief_key in st.session_state:
        with st.expander("Gemini에 전달되는 문구 확인"):
            st.json(st.session_state[brief_key])
    if png_key in st.session_state and meta_key in st.session_state:
        meta = st.session_state[meta_key]
        if meta.get("signature") == signature and meta.get("template_index") == selected_template.index:
            st.image(st.session_state[png_key], caption=f"{meta['template_title']} · {meta['source_title']}", use_container_width=True)
            st.download_button(
                "PNG 다운로드",
                data=st.session_state[png_key],
                file_name=meta["file_name"],
                mime="image/png",
                use_container_width=True,
                key=f"{key_prefix}_download_infographic",
            )


def render_styles() -> None:
    st.markdown(
        """
        <style>
        :root { --red:#e03030; --red-dark:#ba1f24; --ink:#242128; --muted:#7d7784; --line:#f6e4e4; }
        .stApp {
            background:
                radial-gradient(circle at 44% 38%, rgba(255,221,150,.28), transparent 20rem),
                radial-gradient(circle at 69% 39%, rgba(255,90,95,.14), transparent 22rem),
                #fff;
        }
        header[data-testid="stHeader"] { background:rgba(255,255,255,.88); border-bottom:1px solid #eee; backdrop-filter:blur(10px); }
        section[data-testid="stSidebar"], [data-testid="collapsedControl"] { display:none; }
        .block-container { max-width:1080px; margin-left:auto; margin-right:auto; padding-top:4.8rem; padding-bottom:4rem; }
        .hero { text-align:center; margin:.5rem auto 2.15rem; }
        .hero h1 { color:#232027; font-size:clamp(2.1rem, 5vw, 3.4rem); line-height:1.1; font-weight:900; letter-spacing:0; margin:0; }
        .hero .blue { color:#2563df; }
        div[data-testid="stPills"],
        div[data-testid="stButtonGroup"] {
            display:flex !important;
            justify-content:center !important;
            gap:1.25rem !important;
        }
        div[data-testid="stPills"] button,
        div[data-testid="stButtonGroup"] button,
        button[data-testid^="stBaseButton-pills"] {
            min-height:3.25rem !important;
            padding:.65rem 1.15rem !important;
        }
        div[data-testid="stPills"] button,
        div[data-testid="stPills"] button *,
        div[data-testid="stPills"] [role="radio"],
        div[data-testid="stPills"] [role="radio"] *,
        div[data-testid="stButtonGroup"] button,
        div[data-testid="stButtonGroup"] button *,
        button[data-testid^="stBaseButton-pills"],
        button[data-testid^="stBaseButton-pills"] * {
            font-size:1.5rem !important;
            line-height:1.12 !important;
            font-weight:900 !important;
            letter-spacing:0 !important;
        }
        div[data-testid="stButton"] > button {
            background:linear-gradient(135deg, var(--red), #ff5a5f) !important;
            color:#fff !important;
            border:1px solid rgba(224,48,48,.18) !important;
            border-radius:12px !important;
            font-weight:900 !important;
            box-shadow:0 10px 24px rgba(224,48,48,.18) !important;
        }
        div[data-testid="stButton"] > button:hover {
            background:linear-gradient(135deg, var(--red-dark), var(--red)) !important;
            color:#fff !important;
            border-color:rgba(186,31,36,.24) !important;
        }
        div[data-testid="stButton"] > button:disabled {
            background:#f4c8ca !important;
            color:#fff !important;
            box-shadow:none !important;
            opacity:.7 !important;
        }
        section[data-testid="stFileUploader"] {
            margin-bottom:.75rem;
        }
        section[data-testid="stFileUploaderDropzone"] {
            min-height:142px;
            border:1px solid #f0dada !important;
            border-radius:12px !important;
            background:rgba(255,255,255,.92) !important;
            display:flex;
            align-items:center;
            justify-content:center;
            padding:1rem !important;
        }
        section[data-testid="stFileUploaderDropzone"] button {
            background:#f2f3f5 !important;
            color:#4b4652 !important;
            border:1px solid #d8dbe0 !important;
            border-radius:10px !important;
            font-weight:900 !important;
            box-shadow:none !important;
        }
        section[data-testid="stFileUploaderDropzone"] button:hover {
            background:#e9ebef !important;
            color:#34303a !important;
            border-color:#cfd3da !important;
        }
        section[data-testid="stFileUploaderDropzone"] div,
        section[data-testid="stFileUploaderDropzone"] span,
        section[data-testid="stFileUploaderDropzone"] small {
            color:#34303a !important;
            font-size:.95rem !important;
        }
        div[data-testid="stFileUploader"] svg,
        div[data-testid="stFileUploader"] [data-testid="stIconMaterial"],
        div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] svg,
        div[data-testid="stFileUploader"] [data-testid="stFileUploaderFile"] [data-testid="stIconMaterial"] {
            color:#6f6976 !important;
            fill:#6f6976 !important;
            stroke:#6f6976 !important;
        }
        div[data-testid="stVerticalBlockBorderWrapper"] { border-color:#ebe4f3; border-radius:18px; background:rgba(255,255,255,.94); box-shadow:0 24px 70px rgba(66,44,95,.10); }
        .question-label { font-size:1.2rem; font-weight:900; color:var(--ink); margin-bottom:.7rem; }
        .result-title { margin:1.7rem 0 .75rem; font-size:1.15rem; font-weight:900; color:var(--ink); }
        .result-card { border:1px solid #f0dada; border-radius:12px; background:rgba(255,255,255,.92); padding:1.15rem 1.25rem; margin:.75rem 0; line-height:1.75; color:#34303a; }
        .result-meta { color:#8f8795; font-weight:700; font-size:.92rem; margin-bottom:.55rem; }
        .template-title-text {
            height:1.45rem;
            line-height:1.45rem;
            color:#5f5867;
            font-weight:900;
            text-align:center;
            margin:.5rem 0 .35rem;
            white-space:nowrap;
            overflow:hidden;
            text-overflow:ellipsis;
        }
        .template-thumb {
            display:block;
            width:100%;
            aspect-ratio:16/9;
            object-fit:cover;
            border:3px solid #f1d4d5;
            border-radius:10px;
            background:#fff;
        }
        div[data-testid="stCheckbox"] {
            position:relative;
            z-index:10;
            width:1.45rem;
            height:0;
            margin:0;
            transform:translate(.55rem, 2.05rem);
        }
        div[data-testid="stCheckbox"] label {
            width:1.45rem;
            height:1.45rem;
            min-height:1.45rem;
            padding:0;
            border-radius:999px;
            background:transparent;
        }
        div[data-testid="stCheckbox"] label p { display:none; }
        div[data-testid="stCheckbox"] [data-testid="stMarkdownContainer"] { display:none; }
        div[data-testid="stCheckbox"] label > div:first-child {
            width:1.28rem;
            height:1.28rem;
            border-radius:999px;
            background:rgba(255,255,255,.08);
            box-shadow:0 0 0 1.5px rgba(255,255,255,.98), 0 2px 8px rgba(0,0,0,.22);
        }
        .working-line { display:flex; align-items:center; justify-content:center; gap:.55rem; width:100%; color:#ba1f24; font-weight:900; padding:.7rem 0; text-align:center; }
        .working-icon { width:1rem; height:1rem; border:3px solid #ffd2d3; border-top-color:#ba1f24; border-radius:999px; animation:infographic-spin .85s linear infinite; }
        @keyframes infographic-spin { from { transform:rotate(0deg); } to { transform:rotate(360deg); } }
        mark { background:#fff0b8; border-radius:4px; padding:0 .12rem; }
        @media (max-width:800px) { .block-container { padding-top:2.8rem; } .hero h1 { font-size:2.15rem; } }
        </style>
        """,
        unsafe_allow_html=True,
    )


def submit_question() -> None:
    st.session_state.submitted_question = st.session_state.question_text.strip()


def reset_chat() -> None:
    st.session_state.question_text = ""
    st.session_state.submitted_question = ""
    st.session_state.show_pdf_text = False


def show_pdf_text() -> None:
    st.session_state.show_pdf_text = True


def reset_youtube_result() -> None:
    st.session_state.youtube_result = {}
    st.session_state.youtube_question_text = ""
    st.session_state.submitted_youtube_question = ""
    for suffix in ("infographic_png", "infographic_meta", "infographic_brief"):
        st.session_state.pop(f"youtube_{suffix}", None)


def submit_youtube_question() -> None:
    st.session_state.submitted_youtube_question = st.session_state.youtube_question_text.strip()


def reset_youtube_chat() -> None:
    st.session_state.youtube_question_text = ""
    st.session_state.submitted_youtube_question = ""


def switch_tool_mode() -> None:
    next_mode = st.session_state.get("menu_mode", "pdf")
    if next_mode in ("pdf", "youtube"):
        st.session_state.tool_mode = next_mode
        st.session_state._last_query_mode = next_mode
        st.query_params["mode"] = next_mode


def init_state() -> None:
    if "submitted_question" not in st.session_state:
        st.session_state.submitted_question = ""
    if "question_text" not in st.session_state:
        st.session_state.question_text = ""
    if "show_pdf_text" not in st.session_state:
        st.session_state.show_pdf_text = False
    if "youtube_url" not in st.session_state:
        st.session_state.youtube_url = ""
    if "youtube_result" not in st.session_state:
        st.session_state.youtube_result = {}
    if "youtube_question_text" not in st.session_state:
        st.session_state.youtube_question_text = ""
    if "submitted_youtube_question" not in st.session_state:
        st.session_state.submitted_youtube_question = ""

    requested_mode = st.query_params.get("mode", "pdf")
    if isinstance(requested_mode, list):
        requested_mode = requested_mode[0] if requested_mode else "pdf"
    requested_mode = requested_mode if requested_mode in ("pdf", "youtube") else "pdf"
    if "tool_mode" not in st.session_state or st.session_state.get("_last_query_mode") != requested_mode:
        st.session_state.tool_mode = requested_mode
        st.session_state.menu_mode = requested_mode
        st.session_state._last_query_mode = requested_mode
    if "menu_mode" not in st.session_state or st.session_state.menu_mode not in ("pdf", "youtube"):
        st.session_state.menu_mode = "pdf"


def render_header() -> None:
    st.markdown(
        """
        <div class="hero">
          <h1><span class="blue">PDF부터 유튜브까지</span><br />가장 빠른 AI 요약 서비스</h1>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_tool_box() -> tuple[list[object], bool]:
    uploaded_files: list[object] = []
    summarize_youtube = False
    with st.container(border=True):
        mode_labels = {"pdf": "PDF 문서 분석", "youtube": "유튜브 영상 요약"}
        st.pills(
            "분석 도구 선택",
            ["pdf", "youtube"],
            default=st.session_state.menu_mode,
            format_func=lambda mode: mode_labels[mode],
            label_visibility="collapsed",
            width="stretch",
            key="menu_mode",
            on_change=switch_tool_mode,
        )
        if st.session_state.menu_mode in mode_labels and st.session_state.tool_mode != st.session_state.menu_mode:
            st.session_state.tool_mode = st.session_state.menu_mode

        st.markdown('<div style="height:1.25rem;"></div>', unsafe_allow_html=True)
        if st.session_state.tool_mode == "youtube":
            st.markdown('<div class="question-label">유튜브 영상 URL을 입력해 요약을 시작하세요</div>', unsafe_allow_html=True)
            st.text_area(
                "유튜브 URL",
                placeholder="유튜브 URL을 한 줄에 하나씩 입력하세요.",
                height=132,
                key="youtube_url",
                on_change=reset_youtube_result,
                label_visibility="collapsed",
            )
            summarize_youtube = st.button("영상 요약하기", type="primary", use_container_width=True)
        else:
            upload_column, question_column = st.columns([1, 1], gap="large")
            with upload_column:
                st.markdown('<div class="question-label">PDF 문서를 업로드하세요</div>', unsafe_allow_html=True)
                uploaded_files = st.file_uploader(
                    "PDF 파일",
                    type=["pdf"],
                    accept_multiple_files=True,
                    label_visibility="collapsed",
                )
                if uploaded_files and len(uploaded_files) > 5:
                    st.warning("PDF는 최대 5개까지만 분석합니다. 앞의 5개 파일만 사용합니다.")
                    uploaded_files = uploaded_files[:5]
                st.button("PDF 내용 읽기", use_container_width=True, disabled=not uploaded_files, on_click=show_pdf_text)
            with question_column:
                st.markdown('<div class="question-label">이 문서에 대한 질문을 입력하세요</div>', unsafe_allow_html=True)
                st.text_area(
                    "질문",
                    placeholder="문서 내용에 대해 질문하세요.",
                    height=142,
                    label_visibility="collapsed",
                    key="question_text",
                )
                button_left, button_right = st.columns([1, 1], gap="small")
                with button_left:
                    st.button("질문하기", type="primary", use_container_width=True, on_click=submit_question)
                with button_right:
                    st.button("대화 초기화", use_container_width=True, on_click=reset_chat)
    return uploaded_files, summarize_youtube


def render_youtube_page(summarize_youtube: bool) -> None:
    youtube_urls = parse_youtube_urls(st.session_state.youtube_url)
    youtube_signature = "\n".join(youtube_urls)
    cached_result = st.session_state.youtube_result
    cached_is_current = (
        cached_result.get("url_signature") == youtube_signature
        and cached_result.get("result_version") == YOUTUBE_RESULT_VERSION
    )
    if not summarize_youtube and not cached_is_current:
        if cached_result:
            reset_youtube_result()
        st.info("유튜브 영상 URL을 입력하고 '영상 요약하기' 버튼을 누르세요.")
        st.stop()

    if summarize_youtube:
        if not youtube_urls:
            st.error("유효한 유튜브 URL을 한 개 이상 입력해 주세요.")
            st.stop()
        reset_youtube_result()
        summary_items: list[dict[str, str]] = []
        for index, video_url in enumerate(youtube_urls, start=1):
            video_id = extract_youtube_video_id(video_url) or ""
            title = fetch_youtube_title(video_url, video_id)
            transcript_text = ""
            transcript_error = ""
            summary_text = ""
            summary_basis = ""
            summary_ok = False
            try:
                with st.spinner(f"{index}. {title} 자막을 가져오는 중입니다..."):
                    transcript_text = fetch_youtube_transcript(video_id)
            except Exception as exc:
                transcript_error = str(exc)
            if transcript_text and os.getenv("OPENAI_API_KEY"):
                try:
                    with st.spinner(f"{index}. {title} 요약을 생성하는 중입니다..."):
                        summary_text = generate_youtube_summary(video_url, transcript_text, os.getenv("OPENAI_MODEL", ANSWER_MODEL))
                    summary_basis = f"유튜브 공개 자막 기반 · video_id {html.escape(video_id)} · 자막 {len(transcript_text):,}자"
                    summary_ok = True
                except Exception as exc:
                    transcript_error = f"자막 기반 요약 실패: {exc}"
            if not summary_text:
                if not os.getenv("GEMINI_API_KEY"):
                    summary_text = "요약을 생성하지 못했습니다. 자막이 없고 Gemini API 설정도 없어 영상 분석을 진행할 수 없습니다."
                    summary_basis = "자막 없음 또는 자막 기반 요약 실패"
                else:
                    try:
                        with st.spinner(f"{index}. Gemini가 {title} 영상을 분석하는 중입니다..."):
                            summary_text = generate_gemini_youtube_summary(video_url, os.getenv("GEMINI_VIDEO_MODEL", GEMINI_VIDEO_MODEL))
                        summary_basis = f"Gemini 영상 분석 기반 · video_id {html.escape(video_id)}"
                        summary_ok = True
                    except Exception:
                        summary_text = "요약을 생성하지 못했습니다. 자막이 없고 영상 길이 또는 토큰 한도 때문에 Gemini 분석도 실패했습니다."
                        summary_basis = "자막 없음 또는 영상 분석 한도 초과"
            summary_items.append(
                {
                    "url": video_url,
                    "video_id": video_id,
                    "title": title,
                    "transcript_text": transcript_text,
                    "transcript_error": transcript_error,
                    "summary_text": summary_text,
                    "summary_basis": summary_basis,
                    "summary_ok": str(summary_ok),
                }
            )
        st.session_state.youtube_result = {
            "url_signature": youtube_signature,
            "result_version": YOUTUBE_RESULT_VERSION,
            "items": summary_items,
        }
    else:
        summary_items = list(cached_result.get("items", []))

    valid_items = [item for item in summary_items if item.get("summary_ok") == "True"]
    if summary_items:
        st.markdown('<div class="result-title">유튜브 요약 기반 질문</div>', unsafe_allow_html=True)
        if not valid_items:
            st.warning("질문에 사용할 수 있는 유튜브 요약이 없습니다. 자막이 있는 영상이거나 길이가 짧은 영상으로 다시 시도해 주세요.")
        st.text_area(
            "유튜브 요약 질문",
            placeholder="요약된 영상 내용에 대해 질문을 입력하세요.",
            height=142,
            label_visibility="collapsed",
            key="youtube_question_text",
            disabled=not valid_items,
        )
        button_left, button_right = st.columns([1, 1], gap="small")
        with button_left:
            st.button("질문하기", type="primary", use_container_width=True, on_click=submit_youtube_question, disabled=not valid_items)
        with button_right:
            st.button("대화 초기화", use_container_width=True, on_click=reset_youtube_chat)

        submitted_question = st.session_state.submitted_youtube_question
        if submitted_question and valid_items:
            answer_text = ""
            answer_notice = ""
            if os.getenv("OPENAI_API_KEY"):
                try:
                    context_items = tuple((str(item.get("title", "YouTube")), str(item.get("summary_text", ""))) for item in valid_items)
                    with st.spinner("유튜브 요약 내용을 근거로 답변을 작성하는 중입니다..."):
                        answer_text = generate_youtube_answer(submitted_question, context_items, os.getenv("OPENAI_MODEL", ANSWER_MODEL))
                except Exception as exc:
                    answer_notice = f"답변 생성에 실패했습니다: {exc}"
            else:
                answer_notice = "OPENAI_API_KEY가 없어 답변을 생성할 수 없습니다."

            st.markdown('<div class="result-title">현재 질문</div>', unsafe_allow_html=True)
            st.markdown(
                f"""
                <div class="result-card">
                  <div>{html.escape(submitted_question)}</div>
                  <div class="result-meta" style="margin-top:.85rem; margin-bottom:0;">유튜브 요약 내용 기반 · {len(valid_items)}개 영상</div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            st.markdown('<div class="result-title">답변</div>', unsafe_allow_html=True)
            if answer_text:
                _, copy_col = st.columns([12, 1])
                with copy_col:
                    render_copy_button(answer_text, "youtube-answer")
                st.markdown(
                    f"""
                    <div class="result-card">
                      <div>{render_answer_html(answer_text)}</div>
                      <div class="result-meta" style="margin-top:.85rem; margin-bottom:0;">(근거) 유튜브 요약 내용 기반 · {len(valid_items)}개 영상</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            elif answer_notice:
                st.warning(answer_notice)
            st.markdown('<div class="result-title">답변에 사용한 요약</div>', unsafe_allow_html=True)
            for index, item in enumerate(valid_items, start=1):
                st.markdown(
                    f"""
                    <div class="result-card">
                      <div class="result-meta">{index}. {html.escape(str(item.get("title", "YouTube")))}</div>
                      <div>{render_answer_html(str(item.get("summary_text", "")))}</div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

    st.markdown('<div class="result-title">유튜브 영상 요약</div>', unsafe_allow_html=True)
    for index, item in enumerate(summary_items, start=1):
        title = str(item.get("title", f"YouTube {index}"))
        summary_text = str(item.get("summary_text", ""))
        summary_basis = str(item.get("summary_basis", ""))
        title_col, copy_col = st.columns([12, 1])
        with title_col:
            st.markdown(f"#### {html.escape(title)}")
        with copy_col:
            render_copy_button(summary_text, f"youtube-summary-{index}")
        st.markdown(
            f"""
            <div class="result-card">
              <div>{render_answer_html(summary_text)}</div>
              <div class="result-meta" style="margin-top:.85rem; margin-bottom:0;">(근거) {summary_basis}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    combined_summary_text = "\n\n".join(f"[{item.get('title', 'YouTube')}]\n{item.get('summary_text', '')}" for item in valid_items)
    combined_transcript_text = "\n\n".join(
        f"[{item.get('title', 'YouTube')}]\n{item.get('transcript_text', '')}"
        for item in summary_items
        if item.get("transcript_text")
    )
    if combined_transcript_text:
        with st.expander("가져온 유튜브 자막 보기"):
            st.text_area("유튜브 자막", combined_transcript_text, height=320, label_visibility="collapsed")
    render_infographic_section("유튜브 영상", f"YouTube {len(valid_items)}개 영상", combined_summary_text, "youtube")
    st.stop()


def render_pdf_page(uploaded_files: list[object]) -> None:
    uploaded_files = uploaded_files[:5] if uploaded_files else []
    if not uploaded_files:
        st.stop()

    with st.spinner("PDF를 읽는 중입니다..."):
        pages: list[tuple[str, int, str]] = []
        for uploaded_pdf in uploaded_files:
            for page_number, page_text in extract_pages_from_pdf(uploaded_pdf.getvalue()):
                pages.append((uploaded_pdf.name, page_number, page_text))
        chunks = build_chunks(pages)

    if not pages or not chunks:
        st.error("PDF에서 검색 가능한 텍스트를 추출하지 못했습니다. 이미지 PDF라면 OCR 단계가 필요합니다.")
        st.stop()

    submitted_question = st.session_state.submitted_question
    if not submitted_question:
        st.info(f"{len(uploaded_files)}개 PDF를 읽었습니다. 질문을 입력한 뒤 '질문하기' 버튼을 누르세요.")
        if st.session_state.show_pdf_text:
            render_pdf_pages(pages)
        st.stop()

    result_limit = len(pages)
    page_location_results = find_page_location_chunks(submitted_question, chunks, result_limit) if is_page_location_question(submitted_question) else []
    search_notice = ""
    if page_location_results:
        results = page_location_results
        search_mode = "페이지 위치 검색"
    elif os.getenv("OPENAI_API_KEY"):
        try:
            with st.spinner("질문과 PDF 문단의 의미를 비교하는 중입니다..."):
                results = find_semantic_chunks(submitted_question, chunks, min(result_limit, 30))
            search_mode = "임베딩 검색"
        except Exception as exc:
            results = find_relevant_chunks(submitted_question, chunks, result_limit)
            search_mode = "단어 검색"
            search_notice = f"임베딩 검색에 실패해서 단어 검색으로 전환했습니다: {exc}"
    else:
        results = find_relevant_chunks(submitted_question, chunks, result_limit)
        search_mode = "단어 검색"
        search_notice = "OPENAI_API_KEY가 없어 단어 검색으로 실행했습니다."

    answer_text = ""
    answer_notice = ""
    answer_source_pages: list[int] = []
    answer_source_chunks: list[PdfChunk] = []
    if results and os.getenv("OPENAI_API_KEY"):
        try:
            answer_source_chunks = [chunk for chunk, _ in results[:8]]
            answer_context = tuple((chunk.source_name, chunk.page_number, chunk.text) for chunk in answer_source_chunks)
            answer_source_pages = sorted({page for _, page, _ in answer_context})
            with st.spinner("추출한 PDF 텍스트를 근거로 답변을 작성하는 중입니다..."):
                answer_text = generate_answer(submitted_question, answer_context, os.getenv("OPENAI_MODEL", ANSWER_MODEL))
        except Exception as exc:
            answer_notice = f"답변 생성에 실패했습니다. 아래 근거 페이지를 확인해 주세요: {exc}"
    elif results:
        answer_notice = "OPENAI_API_KEY가 없어 답변 생성 없이 근거 페이지만 표시합니다."

    st.markdown('<div class="result-title">현재 질문</div>', unsafe_allow_html=True)
    st.markdown(
        f"""
        <div class="result-card">
          <div>{html.escape(submitted_question)}</div>
          <div class="result-meta" style="margin-top:.85rem; margin-bottom:0;">PyPDFLoader 추출 텍스트 기반 · {len(uploaded_files)}개 문서 · {len(pages)}페이지 · {len(chunks)}개 문단 · {search_mode}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    st.markdown('<div class="result-title">답변</div>', unsafe_allow_html=True)
    if answer_text:
        _, copy_col = st.columns([12, 1])
        with copy_col:
            render_copy_button(answer_text, "pdf-answer")
        st.markdown(
            f"""
            <div class="result-card">
              <div>{render_answer_html(answer_text)}</div>
              <div class="result-meta" style="margin-top:.85rem; margin-bottom:0;">(근거) PyPDFLoader 추출 텍스트 기반 · {format_page_refs(answer_source_pages)} · {format_chunk_refs(answer_source_chunks)}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )
    elif answer_notice:
        st.warning(answer_notice)

    st.markdown('<div class="result-title">답변에 사용한 근거 텍스트</div>', unsafe_allow_html=True)
    if search_notice:
        st.warning(search_notice)
    if not results:
        st.warning("질문과 직접 관련된 문단을 찾지 못했습니다. 질문의 핵심 단어를 조금 더 넣어보세요.")
    else:
        for index, (chunk, score) in enumerate(results, start=1):
            highlighted_text = highlight_terms(chunk.text, submitted_question)
            st.markdown(
                f"""
                <div class="result-card">
                  <div class="result-meta">{index}. {html.escape(chunk.source_name)} · 원본 Page {chunk.page_number} · Chunk {chunk.chunk_number} | {search_mode} relevance {score:.3f}</div>
                  <div>{highlighted_text}</div>
                </div>
                """,
                unsafe_allow_html=True,
            )

    if st.session_state.show_pdf_text:
        render_pdf_pages(pages)
    source_title = ", ".join(uploaded_pdf.name for uploaded_pdf in uploaded_files)
    render_infographic_section("PDF 문서", source_title, source_text_from_pages(pages), "pdf")


def main() -> None:
    load_dotenv()
    load_dotenv(".chatgptkey.env")
    st.set_page_config(page_title="ChatPDF Mini", page_icon="📄", layout="wide")
    render_styles()
    init_state()
    render_header()
    uploaded_files, summarize_youtube = render_tool_box()
    if st.session_state.tool_mode == "youtube":
        render_youtube_page(summarize_youtube)
    render_pdf_page(uploaded_files)


if __name__ == "__main__":
    main()
