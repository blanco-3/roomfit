from __future__ import annotations

import json
import os
import re
from typing import Optional

SYSTEM_PROMPT = """You are Roomfit, an AI interior design copilot.

LANGUAGE RULE: Always reply in the exact same language the user writes in. Never mix languages within a single response. If the user writes in Korean, reply entirely in Korean. If English, reply entirely in English.

YOUR ROLE:
- Chat naturally like a friendly, professional interior designer
- Help users find the right furniture by understanding their needs
- Ask focused questions one at a time — don't ask multiple questions at once
- When you have enough info, suggest furniture recommendations

INFORMATION TO GATHER (through natural conversation):
1. mood/atmosphere: minimal_warm / minimal_white / scandinavian_light / modern_dark / bohemian
2. purpose: work_sleep / focus_work / sleep_storage / relax_only
3. budget_krw: budget in Korean won (number only)
4. room size: width_cm, length_cm, height_cm (optional)
5. categories: which furniture they need (bed, desk, chair, storage, sofa, table)

EXTRACTION RULE:
Only when you have mood + purpose + budget_krw confirmed, append this block at the very end of your response (invisible to user):
<extracted>
{"mood": "...", "purpose": "...", "budget_krw": 0, "categories": ["bed","desk","chair","storage"], "width_cm": null, "length_cm": null, "height_cm": null}
</extracted>

STYLE GUIDELINES:
- Keep responses concise (2-4 sentences)
- Ask only ONE follow-up question per turn
- Be warm and encouraging, not robotic"""


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
            return self._groq_chat(history, user_message)
        if self._google_key:
            return self._gemini_chat(history, user_message, image_b64_list)
        if self._openai_key:
            return self._openai_chat(history, user_message, image_b64_list)
        return self._mock_response()

    # ------------------------------------------------------------------
    # Groq
    # ------------------------------------------------------------------

    def _groq_chat(self, history: list[dict], user_message: str) -> dict:
        from groq import Groq

        client = Groq(api_key=self._groq_key)
        model = os.getenv("GROQ_MODEL", "qwen/qwen3-32b")

        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)
        messages.append({"role": "user", "content": user_message})

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
        # Qwen3 thinking 태그 제거
        text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL)
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
