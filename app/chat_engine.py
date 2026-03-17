from __future__ import annotations

import json
import os
import re
from typing import Optional

SYSTEM_PROMPT = """You are Roomfit, an AI interior design copilot. You help Korean users find real furniture products.

LANGUAGE: Korean only. Never use English words or mix languages.

═══ BUDGET PARSING ═══
Convert all Korean budget expressions to an exact number:
- "N만원" → N * 10000  (예: "30만원" → 300000)
- "N만원대" / "N만원 정도" / "약 N만원" → N * 10000  (예: "10만원대" → 100000)
- "N~M만원" → M * 10000  (예: "50~70만원" → 700000)
- "N백만원" → N * 1000000  (예: "1백만원" → 1000000)
- "N천원" → N * 1000
Always use the upper-end of a range as budget_krw.

═══ EXTRACTION TRIGGER ═══
Emit <extracted> as soon as budget_krw is known. Rules:
1. User gives budget + any other info in ONE message → emit <extracted> immediately, NO question
2. User replies "없어" / "아니요" / "됐어" / "그냥" / "응" / "그래" / "보내" / "좋아" → emit <extracted> immediately
3. NEVER ask a question after emitting <extracted>
4. NEVER emit <extracted> more than once per conversation

═══ AFTER RECOMMENDATION ═══
When the system shows recommendations (after <extracted> is emitted):
- Say ONE warm sentence like "찾아드렸어요! 마음에 드는 게 있으신가요?"
- If user says they don't like it → ask what to change (style? price? color?)
- If user says budget was too low / no results → suggest budget range that works

═══ CATEGORY RULE ═══
- User mentions specific item (소파/침대/책상 etc.) → use ONLY that category
- No item mentioned → use all defaults

═══ MOOD INFERENCE ═══
- 어둡/블랙/다크/검정/모던 → "modern_dark"
- 따뜻/아늑/우드/원목/나무 → "minimal_warm"
- 화이트/밝/심플/깔끔/화사 → "minimal_white"
- 북유럽/스칸디/내추럴/자연 → "scandinavian_light"
- 빈티지/보헤/라탄/이국적 → "bohemian"

═══ PURPOSE INFERENCE ═══
- 휴식/릴렉스/편안/쉬는 → "relax"
- 업무/작업/공부/일 → "work"
- 수면/침실/자는 → "sleep"
- 수납/정리/보관 → "storage"

═══ DEFAULT VALUES ═══
mood: "minimal_warm" | purpose: "work_sleep"
categories: ["bed","desk","chair","storage","sofa","table"]
width_cm / length_cm / height_cm: null

═══ EXTRACTION FORMAT ═══
<extracted>
{"mood": "...", "purpose": "...", "budget_krw": 0, "categories": ["sofa"], "width_cm": null, "length_cm": null, "height_cm": null, "pref_colors": [], "pref_materials": []}
</extracted>

pref_colors: "검정/블랙" → ["black"], "흰색/화이트" → ["white"], "원목/나무색" → ["natural","brown"], "그레이/회색" → ["gray"]
pref_materials: "원목" → ["solid_wood"], "패브릭" → ["fabric"], "벨벳" → ["velvet"], "가죽" → ["leather"]

═══ EXAMPLES ═══
User: "10만원대 검정 1인 소파"
→ <extracted> budget_krw:100000, mood:"modern_dark", purpose:"relax", categories:["sofa"], pref_colors:["black"]
→ reply: "검정 1인 소파 바로 찾아드릴게요!"

User: "50~80만원 사이 북유럽 원룸 꾸미기"
→ <extracted> budget_krw:800000, mood:"scandinavian_light", purpose:"work_sleep", categories:["bed","desk","chair","storage","sofa","table"]
→ reply: "북유럽 스타일로 원룸 가구 찾아드릴게요!"

═══ STYLE ═══
- 1-2 sentences only after emitting <extracted>
- Warm, friendly, casual Korean (존댓말 유지)
- No bullet lists
- No robotic phrases like "물론이죠" "알겠습니다" "도와드리겠습니다\""""


class ChatEngine:
    def __init__(self) -> None:
        self._groq_key = os.getenv("GROQ_API_KEY")
        self._google_key = os.getenv("GOOGLE_API_KEY")
        self._openai_key = os.getenv("OPENAI_API_KEY")

    def chat(
        self,
        history: list[dict],
        user_message: str,
        image_b64_list: Optional[list[str]] = None,
    ) -> dict:
        if self._groq_key:
            return self._groq_chat(history, user_message, image_b64_list)
        if self._google_key:
            return self._gemini_chat(history, user_message, image_b64_list)
        if self._openai_key:
            return self._openai_chat(history, user_message, image_b64_list)
        return self._mock_response()

    # ------------------------------------------------------------------
    # Groq
    # ------------------------------------------------------------------

    def _groq_chat(
        self,
        history: list[dict],
        user_message: str,
        image_b64_list: Optional[list[str]] = None,
    ) -> dict:
        from groq import Groq

        client = Groq(api_key=self._groq_key)

        # 이미지가 있으면 vision 모델 사용
        if image_b64_list:
            model = os.getenv("GROQ_VISION_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct")
            content: list = [{"type": "text", "text": user_message}]
            for b64 in image_b64_list:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
            user_part: object = content
        else:
            model = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")
            user_part = user_message

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_part})

        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                max_tokens=1024,
            )
            raw_reply = response.choices[0].message.content or ""
        except Exception as exc:
            return {"reply": f"AI 응답 오류: {exc}", "extracted": None, "trigger_recommend": False}

        return self._build_result(raw_reply)

    # ------------------------------------------------------------------
    # Gemini
    # ------------------------------------------------------------------

    def _gemini_chat(
        self,
        history: list[dict],
        user_message: str,
        image_b64_list: Optional[list[str]] = None,
    ) -> dict:
        from google import genai
        from google.genai import types

        client = genai.Client(api_key=self._google_key)
        model = os.getenv("GEMINI_MODEL", "gemini-2.0-flash-lite")

        # 히스토리 변환
        contents = []
        for msg in history:
            role = "user" if msg["role"] == "user" else "model"
            contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

        # 현재 메시지 파츠
        parts: list = [types.Part(text=user_message)]
        if image_b64_list:
            import base64
            for b64 in image_b64_list:
                try:
                    parts.append(types.Part(
                        inline_data=types.Blob(mime_type="image/jpeg", data=base64.b64decode(b64))
                    ))
                except Exception:
                    pass
        contents.append(types.Content(role="user", parts=parts))

        try:
            response = client.models.generate_content(
                model=model,
                contents=contents,
                config=types.GenerateContentConfig(system_instruction=SYSTEM_PROMPT),
            )
            raw_reply = response.text or ""
        except Exception as exc:
            return {"reply": f"AI 응답 오류: {exc}", "extracted": None, "trigger_recommend": False}

        return self._build_result(raw_reply)

    # ------------------------------------------------------------------
    # OpenAI (fallback)
    # ------------------------------------------------------------------

    def _openai_chat(
        self,
        history: list[dict],
        user_message: str,
        image_b64_list: Optional[list[str]] = None,
    ) -> dict:
        from openai import OpenAI

        client = OpenAI(api_key=self._openai_key)
        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)

        if image_b64_list:
            content: list = [{"type": "text", "text": user_message}]
            for b64 in image_b64_list:
                content.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}})
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_message})

        try:
            response = client.chat.completions.create(
                model=os.getenv("OPENAI_MODEL", "gpt-4o"),
                messages=messages,
                max_tokens=1024,
            )
            raw_reply = response.choices[0].message.content or ""
        except Exception as exc:
            return {"reply": f"AI 응답 오류: {exc}", "extracted": None, "trigger_recommend": False}

        return self._build_result(raw_reply)

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _build_result(self, raw_reply: str) -> dict:
        extracted = self._parse_extracted(raw_reply)
        clean_reply = self._strip_extracted_tag(raw_reply)
        trigger = extracted is not None and all(
            k in extracted for k in ("mood", "purpose", "budget_krw")
        )
        return {"reply": clean_reply, "extracted": extracted, "trigger_recommend": trigger}

    def _parse_extracted(self, text: str) -> Optional[dict]:
        match = re.search(r"<extracted>\s*(.*?)\s*</extracted>", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except Exception:
            return None

    def _strip_extracted_tag(self, text: str) -> str:
        text = re.sub(r"\s*<extracted>.*?</extracted>", "", text, flags=re.DOTALL)
        # Qwen3 thinking 태그 제거 (닫힘 태그 있는 경우)
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
        # 닫힘 태그 없는 경우 — 이후 전체 제거
        text = re.sub(r"<think>.*", "", text, flags=re.DOTALL | re.IGNORECASE)
        return text.strip()

    def _mock_response(self) -> dict:
        return {
            "reply": (
                "안녕하세요! 저는 Roomfit AI 인테리어 코파일럿이에요. 🏠\n\n"
                "(GOOGLE_API_KEY 또는 OPENAI_API_KEY를 설정해 주세요)\n\n"
                "어떤 방을 꾸미고 싶으신가요?"
            ),
            "extracted": None,
            "trigger_recommend": False,
        }
