import base64
import logging
import os

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI

load_dotenv()

logger = logging.getLogger(__name__)

_GOOGLE_API_KEY = os.environ.get("GOOGLE_API_KEY")
_GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")

if not _GOOGLE_API_KEY:
    raise RuntimeError(
        "GOOGLE_API_KEY is not set. Copy .env.example to .env and add your key "
        "(https://aistudio.google.com/apikey)."
    )


def get_llm(temperature: float = 0.0) -> ChatGoogleGenerativeAI:
    return ChatGoogleGenerativeAI(
        model=_GEMINI_MODEL,
        google_api_key=_GOOGLE_API_KEY,
        temperature=temperature,
    )


def invoke_with_system(system_prompt: str, user_prompt: str) -> str:
    llm = get_llm()
    messages = [
        SystemMessage(content=system_prompt),
        HumanMessage(content=user_prompt),
    ]
    raw = llm.invoke(messages).content
    cleaned = raw.strip().removeprefix("```json").removeprefix("```").removesuffix("```").strip()
    logger.debug("[LLM] system=%s... | raw=%s... | cleaned=%s...",
        system_prompt[:60], raw[:120], cleaned[:120])
    return cleaned


def ask_with_image(prompt: str, image_path: str) -> str:
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode()

    message = HumanMessage(
        content=[
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": f"data:image/png;base64,{image_b64}"},
        ]
    )
    llm = get_llm()
    response = llm.invoke([message])
    return response.content


if __name__ == "__main__":
    llm = get_llm()
    reply = llm.invoke("Reply with OK if this connection works.")
    print(reply.content)
