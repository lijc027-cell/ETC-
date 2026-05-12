from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os


@dataclass(frozen=True)
class Config:
    root: Path
    dashscope_api_key: str
    dashscope_base_url: str
    llm_model: str
    embedding_model: str
    embedding_dim: int
    ssh_host: str
    ssh_port: int
    ssh_user: str
    ssh_password: str
    remote_python: str
    remote_mongo_uri: str
    remote_db: str


def load_config(root: Path | str) -> Config:
    root_path = Path(root)
    _load_dotenv(root_path / ".env")
    return Config(
        root=root_path,
        dashscope_api_key=os.getenv("DASHSCOPE_API_KEY", ""),
        dashscope_base_url=os.getenv("DASHSCOPE_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"),
        llm_model=os.getenv("ETF_AGENT_LLM_MODEL", "qwen-plus"),
        embedding_model=os.getenv("ETF_AGENT_EMBEDDING_MODEL", "text-embedding-v3"),
        embedding_dim=int(os.getenv("ETF_AGENT_EMBEDDING_DIM", "1024")),
        ssh_host=os.getenv("ETF_SSH_HOST", ""),
        ssh_port=int(os.getenv("ETF_SSH_PORT", "22")),
        ssh_user=os.getenv("ETF_SSH_USER", ""),
        ssh_password=os.getenv("ETF_SSH_PASSWORD", ""),
        remote_python=os.getenv("ETF_REMOTE_PYTHON", "[ETF_REMOTE_PYTHON]"),
        remote_mongo_uri=os.getenv("ETF_REMOTE_MONGO_URI", "[ETF_REMOTE_MONGO_URI]"),
        remote_db=os.getenv("ETF_REMOTE_DB", "[ETF_REMOTE_DB]"),
    )


def require_runtime_config(config: Config) -> None:
    missing = []
    if not config.dashscope_api_key:
        missing.append("DASHSCOPE_API_KEY")
    if not config.ssh_password:
        missing.append("ETF_SSH_PASSWORD")
    if missing:
        raise RuntimeError(f"阶段：配置\n错误：缺少 .env 配置项 {', '.join(missing)}")


def require_ssh_config(config: Config) -> None:
    if not config.ssh_password:
        raise RuntimeError("阶段：配置\n错误：缺少 .env 配置项 ETF_SSH_PASSWORD")


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
