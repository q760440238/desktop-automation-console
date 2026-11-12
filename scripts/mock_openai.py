"""极简的 OpenAI 兼容 mock 服务，用来在没有真实 Key 的情况下验证：
- /v1/models 能被拉取并在界面下拉里显示
- /v1/chat/completions 能返回文案

用法：python scripts/mock_openai.py [port]
"""
from __future__ import annotations

import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODELS = [
    {"id": "mock-gpt-4o", "object": "model", "owned_by": "mock"},
    {"id": "mock-deepseek-chat", "object": "model", "owned_by": "mock"},
    {"id": "mock-qwen-plus", "object": "model", "owned_by": "mock"},
    {"id": "text-embedding-3-small", "object": "model", "owned_by": "mock"},
]


class Handler(BaseHTTPRequestHandler):
    def _json(self, code: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        print(f"GET {self.path} auth={self.headers.get('Authorization', '')[:14]}", flush=True)
        if self.path.rstrip("/").endswith("/models"):
            self._json(200, {"object": "list", "data": MODELS})
        else:
            self._json(404, {"error": "not found"})

    def do_POST(self) -> None:  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length).decode("utf-8", "replace") if length else "{}"
        print(f"POST {self.path} {raw[:120]}", flush=True)
        if self.path.rstrip("/").endswith("/chat/completions"):
            self._json(
                200,
                {
                    "id": "chatcmpl-mock",
                    "object": "chat.completion",
                    "model": "mock-gpt-4o",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": "你好，我是通过接口生成的示例文案。"},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 12, "completion_tokens": 9, "total_tokens": 21},
                },
            )
        else:
            self._json(404, {"error": "not found"})

    def log_message(self, fmt: str, *args) -> None:  # 静音默认访问日志
        return


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 19999
    print(f"mock OpenAI on http://127.0.0.1:{port}/v1", flush=True)
    ThreadingHTTPServer(("127.0.0.1", port), Handler).serve_forever()
