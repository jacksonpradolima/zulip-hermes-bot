from __future__ import annotations

import os
import json
import re
import time
import traceback
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import httpx
import zulip
from bs4 import BeautifulSoup
from dotenv import load_dotenv


load_dotenv()

ZULIP_SITE_URL = os.getenv("ZULIP_SITE_URL", "").rstrip("/")
ZULIP_BOT_EMAIL = os.getenv("ZULIP_BOT_EMAIL", "")
ZULIP_API_KEY = os.getenv("ZULIP_API_KEY", "")

ZULIP_ALLOWED_USERS = {
    email.strip().lower()
    for email in os.getenv("ZULIP_ALLOWED_USERS", "").split(",")
    if email.strip()
}

ZULIP_REQUIRE_MENTION = os.getenv("ZULIP_REQUIRE_MENTION", "true").lower() == "true"
ZULIP_FREE_RESPONSE_STREAMS = {
    value.strip().lower()
    for value in os.getenv("ZULIP_FREE_RESPONSE_STREAMS", "").split(",")
    if value.strip()
}
ZULIP_CONTEXT_DEPTH = int(os.getenv("ZULIP_CONTEXT_DEPTH", "50"))
ZULIP_CATCHUP = os.getenv("ZULIP_CATCHUP", "false").lower() in {"true", "1", "yes"}
ZULIP_CATCHUP_MAX_MESSAGES = int(os.getenv("ZULIP_CATCHUP_MAX_MESSAGES", "100"))
ZULIP_CATCHUP_WATERMARKS = Path(
    os.getenv(
        "ZULIP_CATCHUP_WATERMARKS",
        str(Path(__file__).with_name("zulip_catchup_watermarks.json")),
    )
)

HERMES_API_URL = os.getenv(
    "HERMES_API_URL",
    "http://127.0.0.1:8642/v1/chat/completions",
)
HERMES_API_KEY = os.getenv("HERMES_API_KEY", "")
HERMES_MODEL = os.getenv("HERMES_MODEL", "hermes-agent")

TIMEZONE = ZoneInfo("America/Sao_Paulo")
MAX_ZULIP_MESSAGE_LENGTH = 3900


def require_env() -> None:
    missing = []

    for name, value in {
        "ZULIP_SITE_URL": ZULIP_SITE_URL,
        "ZULIP_BOT_EMAIL": ZULIP_BOT_EMAIL,
        "ZULIP_API_KEY": ZULIP_API_KEY,
        "HERMES_API_KEY": HERMES_API_KEY,
    }.items():
        if not value:
            missing.append(name)

    if missing:
        raise SystemExit(f"Missing required env vars: {', '.join(missing)}")

    if not ZULIP_ALLOWED_USERS:
        raise SystemExit(
            "ZULIP_ALLOWED_USERS is empty. Add your Zulip user email to .env."
        )


def html_to_text(value: str) -> str:
    return BeautifulSoup(value or "", "html.parser").get_text(" ", strip=True)


def chunk_text(text: str, size: int = MAX_ZULIP_MESSAGE_LENGTH) -> list[str]:
    text = text.strip()
    if not text:
        return ["_Sem resposta._"]

    chunks = []
    while len(text) > size:
        split_at = text.rfind("\n", 0, size)
        if split_at == -1:
            split_at = size
        chunks.append(text[:split_at].strip())
        text = text[split_at:].strip()

    if text:
        chunks.append(text)

    return chunks


def is_stream_message(msg: dict) -> bool:
    return msg.get("type") == "stream"


def is_dm_message(msg: dict) -> bool:
    return msg.get("type") in {"private", "direct"}


def get_stream_name(msg: dict) -> str:
    display_recipient = msg.get("display_recipient")

    if isinstance(display_recipient, str):
        return display_recipient

    # Fallbacks for different Zulip versions
    return msg.get("stream") or msg.get("channel") or ""


def get_topic(msg: dict) -> str:
    return msg.get("subject") or msg.get("topic") or "(no topic)"


class CatchupState:
    """Small forward-only JSON watermark store for optional missed-message catch-up."""

    def __init__(self, path: Path):
        self.path = path

    def read(self) -> dict[str, int]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        if not isinstance(data, dict):
            return {}
        clean: dict[str, int] = {}
        for key, value in data.items():
            try:
                numeric = int(value)
            except (TypeError, ValueError):
                continue
            if numeric > 0:
                clean[str(key)] = numeric
        return clean

    def advance(self, stream_name: str, message_id: int) -> None:
        if not stream_name or message_id <= 0:
            return
        data = self.read()
        if data.get(stream_name, 0) >= message_id:
            return
        data[stream_name] = int(message_id)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)


def stream_requires_mention(stream_name: str, stream_id: int | str | None = None) -> bool:
    if not ZULIP_REQUIRE_MENTION:
        return False
    stream_key = (stream_name or "").strip().lower()
    stream_id_key = str(stream_id or "").strip().lower()
    return not (
        stream_key in ZULIP_FREE_RESPONSE_STREAMS
        or stream_id_key in ZULIP_FREE_RESPONSE_STREAMS
    )


def was_bot_mentioned(msg: dict, bot_user_id: int, bot_full_name: str) -> bool:
    flags = set(msg.get("flags") or [])

    if "mentioned" in flags or "wildcard_mentioned" in flags:
        return True

    content = msg.get("content", "")
    text = html_to_text(content).lower()

    if f'data-user-id="{bot_user_id}"' in content:
        return True

    if bot_full_name and bot_full_name.lower() in text:
        return True

    return False


def clean_user_text(msg: dict, bot_full_name: str) -> str:
    text = html_to_text(msg.get("content", ""))

    # Remove common rendered mention forms.
    if bot_full_name:
        text = text.replace(f"@{bot_full_name}", "")
        text = text.replace(bot_full_name, "")

    text = re.sub(r"@\*\*[^*]+\*\*", "", text)
    return text.strip()


def format_context_message(msg: dict) -> str:
    ts = datetime.fromtimestamp(msg["timestamp"], TIMEZONE).strftime("%Y-%m-%d %H:%M")
    sender = msg.get("sender_full_name") or msg.get("sender_email") or "Unknown"
    topic = get_topic(msg)
    content = html_to_text(msg.get("content", ""))

    return f"- [{ts}] {sender} | {topic}: {content}"


def fetch_recent_topic_context(client: zulip.Client, msg: dict, bot_email: str) -> str:
    if not is_stream_message(msg):
        return ""

    stream_name = get_stream_name(msg)
    topic = get_topic(msg)

    if not stream_name or not topic:
        return ""

    result = client.get_messages(
        {
            "anchor": msg["id"],
            "num_before": max(ZULIP_CONTEXT_DEPTH, 0),
            "num_after": 0,
            "narrow": [
                {"operator": "stream", "operand": stream_name},
                {"operator": "topic", "operand": topic},
            ],
        }
    )

    if result.get("result") != "success":
        return f"[Failed to fetch Zulip context: {result}]"

    lines = []
    for item in result.get("messages", []):
        if item.get("id") == msg.get("id"):
            continue

        if item.get("sender_email", "").lower() == bot_email.lower():
            continue

        content = html_to_text(item.get("content", ""))
        if not content:
            continue

        lines.append(format_context_message(item))

    if not lines:
        return ""

    return "\n".join(
        [
            f"Recent messages in Zulip stream/topic `{stream_name} / {topic}`:",
            *lines,
        ]
    )


def build_session_key(msg: dict) -> str:
    if is_stream_message(msg):
        stream_id = msg.get("stream_id", "unknown-stream")
        topic = get_topic(msg)
        sender = msg.get("sender_email", "unknown-user")
        return f"zulip:stream:{stream_id}:{topic}:user:{sender}"[:240]

    sender = msg.get("sender_email", "unknown-user")
    return f"zulip:dm:{sender}"[:240]


def stream_name_from_message(msg: dict) -> str:
    recipient = msg.get("display_recipient")
    if isinstance(recipient, str):
        return recipient
    return get_stream_name(msg)


def update_catchup_watermark(state: CatchupState, msg: dict) -> None:
    if not is_stream_message(msg):
        return
    stream_name = stream_name_from_message(msg).lower()
    msg_id = int(msg.get("id", 0) or 0)
    state.advance(stream_name, msg_id)


def run_missed_message_catchup(client: zulip.Client, state: CatchupState, handle_message) -> None:
    """
    Optional bounded catch-up for stream messages missed while the bot was down.

    First run for a stream records the newest seen message as baseline and does
    not replay older history. Later runs replay messages after the stored
    watermark through the same handler as live messages.
    """
    if not ZULIP_CATCHUP:
        return

    try:
        streams_result = client.get_streams()
    except Exception:
        traceback.print_exc()
        return
    if streams_result.get("result") != "success":
        print(f"[catchup] failed to list streams: {streams_result.get('msg', 'unknown error')}")
        return

    watermarks = state.read()
    for stream in streams_result.get("streams", []):
        stream_name = str(stream.get("name") or "").lower()
        if not stream_name:
            continue
        watermark = watermarks.get(stream_name, 0)
        try:
            if watermark <= 0:
                result = client.get_messages(
                    {
                        "anchor": "newest",
                        "num_before": 1,
                        "num_after": 0,
                        "narrow": [{"operator": "stream", "operand": stream_name}],
                        "apply_markdown": False,
                    }
                )
                if result.get("result") == "success":
                    messages = result.get("messages", [])
                    newest = max((int(m.get("id", 0) or 0) for m in messages), default=0)
                    state.advance(stream_name, newest)
                continue

            result = client.get_messages(
                {
                    "anchor": watermark + 1,
                    "num_before": 0,
                    "num_after": max(1, ZULIP_CATCHUP_MAX_MESSAGES),
                    "narrow": [{"operator": "stream", "operand": stream_name}],
                    "apply_markdown": False,
                }
            )
            if result.get("result") != "success":
                continue
            replayed = 0
            for msg in result.get("messages", []):
                msg_id = int(msg.get("id", 0) or 0)
                if msg_id <= watermark:
                    continue
                handle_message(msg)
                update_catchup_watermark(state, msg)
                replayed += 1
            if replayed:
                print(f"[catchup] replayed {replayed} missed message(s) in stream {stream_name}")
        except Exception:
            traceback.print_exc()


def call_hermes(user_text: str, context: str, session_key: str) -> str:
    system_prompt = """
Você é um assistente Hermes dentro do Zulip.

Regras:
- Responda no idioma da mensagem do usuário.
- Seja objetivo, operacional e útil.
- Quando houver contexto recente do tópico, use esse contexto como fonte principal.
- Para pedidos como "prioridades de hoje", extraia: prioridades, bloqueios, responsáveis, decisões e respostas pendentes.
- Não invente mensagens, decisões ou responsáveis que não apareçam no contexto.
- Não diga que acessou canais fora do escopo atual.
- Não exponha secrets, tokens ou dados sensíveis.
""".strip()

    messages = [
        {"role": "system", "content": system_prompt},
    ]

    if context:
        messages.append(
            {
                "role": "system",
                "content": context,
            }
        )

    messages.append(
        {
            "role": "user",
            "content": user_text,
        }
    )

    headers = {
        "Authorization": f"Bearer {HERMES_API_KEY}",
        "Content-Type": "application/json",
        "X-Hermes-Session-Key": session_key,
    }

    payload = {
        "model": HERMES_MODEL,
        "messages": messages,
        "stream": False,
    }

    with httpx.Client(timeout=180.0) as http:
        response = http.post(HERMES_API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

    return data["choices"][0]["message"]["content"]


def send_reply(client: zulip.Client, source_msg: dict, content: str) -> None:
    chunks = chunk_text(content)

    for chunk in chunks:
        if is_stream_message(source_msg):
            request = {
                "type": "stream",
                "to": get_stream_name(source_msg),
                "topic": get_topic(source_msg),
                "content": chunk,
            }
        else:
            request = {
                "type": "private",
                "to": [source_msg["sender_email"]],
                "content": chunk,
            }

        result = client.send_message(request)

        # Compatibility fallback for older Zulip servers that expect "subject".
        if (
            result.get("result") != "success"
            and is_stream_message(source_msg)
            and "topic" in request
        ):
            request["subject"] = request.pop("topic")
            result = client.send_message(request)

        if result.get("result") != "success":
            print(f"[send_message failed] {result}")


def main() -> None:
    require_env()

    client = zulip.Client(
        site=ZULIP_SITE_URL,
        email=ZULIP_BOT_EMAIL,
        api_key=ZULIP_API_KEY,
    )

    profile = client.get_profile()
    if profile.get("result") != "success":
        raise SystemExit(f"Failed to authenticate bot: {profile}")

    bot_user_id = profile["user_id"]
    bot_full_name = profile.get("full_name") or ZULIP_BOT_EMAIL

    print(
        f"Connected to Zulip as {bot_full_name} "
        f"<{ZULIP_BOT_EMAIL}> user_id={bot_user_id}"
    )
    print("Waiting for messages... Press Ctrl+C to stop.")

    catchup_state = CatchupState(ZULIP_CATCHUP_WATERMARKS)

    def handle_message(msg: dict) -> None:
        try:
            if is_stream_message(msg):
                update_catchup_watermark(catchup_state, msg)

            sender_email = (msg.get("sender_email") or "").lower()

            if sender_email == ZULIP_BOT_EMAIL.lower():
                return

            if sender_email not in ZULIP_ALLOWED_USERS:
                print(f"[ignored] sender not allowed: {sender_email}")
                return

            if is_stream_message(msg):
                if stream_requires_mention(get_stream_name(msg), msg.get("stream_id")) and not was_bot_mentioned(
                    msg,
                    bot_user_id,
                    bot_full_name,
                ):
                    return

            user_text = clean_user_text(msg, bot_full_name)
            if not user_text:
                return

            where = (
                f"{get_stream_name(msg)} / {get_topic(msg)}"
                if is_stream_message(msg)
                else f"DM from {sender_email}"
            )

            print(f"[message] {where}: {user_text}")

            context = fetch_recent_topic_context(client, msg, ZULIP_BOT_EMAIL)
            session_key = build_session_key(msg)

            answer = call_hermes(
                user_text=user_text,
                context=context,
                session_key=session_key,
            )

            send_reply(client, msg, answer)

        except Exception:
            traceback.print_exc()
            try:
                send_reply(
                    client,
                    msg,
                    "Erro ao processar essa mensagem. Veja o terminal do Hermes/Zulip bot.",
                )
            except Exception:
                pass

    while True:
        try:
            run_missed_message_catchup(client, catchup_state, handle_message)
            client.call_on_each_message(handle_message)
        except KeyboardInterrupt:
            print("Stopping.")
            break
        except Exception:
            print("[event loop error] reconnecting in 5 seconds...")
            traceback.print_exc()
            time.sleep(5)


if __name__ == "__main__":
    main()