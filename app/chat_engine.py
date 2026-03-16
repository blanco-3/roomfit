from __future__ import annotations

import json
import os
import re
from typing import Optional

SYSTEM_PROMPT = """당신은 Roomfit AI 인테리어 코파일럿입니다.
사용자가 방 꾸미기에 대해 이야기하면 친근하고 전문적인 인테리어 전문가처럼 대화하세요.

역할:
- 자연스러운 대화로 방의 분위기/용도/예산/원하는 가구를 파악하세요
- 사진이 첨부되면 방의 현재 상태, 특징, 개선점을 구체적으로 설명하세요
- 필요한 정보가 모이면 가구 추천을 제안하세요

정보 추출:
대화에서 아래 항목들을 파악할 수 있을 때만, 응답 맨 끝에 다음 형식으로 포함하세요:
<extracted>
{
  "mood": "minimal_warm",
  "purpose": "work_sleep",
  "budget_krw": 1200000,
  "categories": ["bed", "desk", "chair", "storage"],
  "width_cm": 280,
  "length_cm": 340,
  "height_cm": 240
}
</extracted>

mood 값: minimal_warm / minimal_white / scandinavian_light / modern_dark / bohemian
purpose 값: work_sleep / focus_work / sleep_storage / relax_only
categories: bed, desk, chair, storage, sofa, shelf, lamp, wardrobe 중 선택

규칙:
- mood, purpose, budget_krw 세 가지가 모두 있어야 <extracted>를 포함하세요
- 방 크기(width_cm, length_cm)는 알 수 없으면 생략하세요
- categories는 사용자가 언급하지 않으면 기본값 ["bed", "desk", "chair", "storage"]를 사용하세요
- <extracted> 태그는 절대 응답 본문에 보이지 않게 처리됩니다"""


class ChatEngine:
    def __init__(self) -> None:
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            from openai import OpenAI  # lazy import
            self.client = OpenAI(api_key=api_key)
        else:
            self.client = None
        self.model = os.getenv("OPENAI_MODEL", "gpt-4o")

    def chat(
        self,
        history: list[dict],
        user_message: str,
        image_b64_list: Optional[list[str]] = None,
    ) -> dict:
        """멀티턴 대화 처리.

        Args:
            history: 이전 대화 [{"role": "user/assistant", "content": "..."}]
            user_message: 현재 사용자 메시지
            image_b64_list: base64 인코딩된 이미지 리스트 (선택)

        Returns:
            {
                "reply": str,               # 표시할 AI 응답 (extracted 태그 제거됨)
                "extracted": dict | None,   # 추출된 방 파라미터
                "trigger_recommend": bool,  # 추천 실행 여부
            }
        """
        if not self.client:
            return self._mock_response()

        messages: list[dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(history)

        # 현재 메시지 구성 (이미지 첨부 여부에 따라)
        if image_b64_list:
            content: list = [{"type": "text", "text": user_message}]
            for b64 in image_b64_list:
                content.append({
                    "type": "image_url",
                    "image_url": {"url": f"data:image/jpeg;base64,{b64}"},
                })
            messages.append({"role": "user", "content": content})
        else:
            messages.append({"role": "user", "content": user_message})

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=messages,
                max_tokens=1024,
            )
            raw_reply = response.choices[0].message.content or ""
        except Exception as exc:
            return {
                "reply": f"AI 응답 오류: {exc}",
                "extracted": None,
                "trigger_recommend": False,
            }

        extracted = self._parse_extracted(raw_reply)
        clean_reply = self._strip_extracted_tag(raw_reply)

        trigger = extracted is not None and all(
            k in extracted for k in ("mood", "purpose", "budget_krw")
        )

        return {
            "reply": clean_reply,
            "extracted": extracted,
            "trigger_recommend": trigger,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _parse_extracted(self, text: str) -> Optional[dict]:
        match = re.search(r"<extracted>\s*(.*?)\s*</extracted>", text, re.DOTALL)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except Exception:
            return None

    def _strip_extracted_tag(self, text: str) -> str:
        return re.sub(r"\s*<extracted>.*?</extracted>", "", text, flags=re.DOTALL).strip()

    def _mock_response(self) -> dict:
        return {
            "reply": (
                "안녕하세요! 저는 Roomfit AI 인테리어 코파일럿이에요. 🏠\n\n"
                "(현재 OPENAI_API_KEY가 설정되지 않아 데모 모드로 동작합니다)\n\n"
                "어떤 방을 꾸미고 싶으신가요? 분위기, 용도, 예산을 알려주시면 가구를 추천해 드릴게요!"
            ),
            "extracted": None,
            "trigger_recommend": False,
        }
