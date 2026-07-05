"""配置加载器模块 —— 统一管理应用所有 YAML 配置的加载、解析与访问。

功能流程:
  1. 加载 .env 环境变量（可选 dotenv）
  2. 解析 config/ 目录下各子配置文件（llm / embed / db / session / auth / logging）
  3. 扫描 config/workflows/<产品线>/ 下的 workflow.yaml 和节点 yaml
  4. 组装为 AppConfig 单例，供全局访问

环境变量插值:
  所有 YAML 值中的 ${VAR} 模式会自动替换为同名环境变量的值。
"""

from __future__ import annotations  # 推迟类型注解求值，支持前向引用

import os
import re
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from src.db.base import DBConfig, DBPoolConfig

# ---------------------------------------------------------------------------
# 常量 & 模块级变量
# ---------------------------------------------------------------------------

_ENV_PATTERN = re.compile(r"\$\{([^}]+)\}")  # 匹配 ${VAR_NAME} 环境变量占位符

_APP_CONFIG: AppConfig | None = None  # 应用配置全局单例


# ---------------------------------------------------------------------------
# 配置数据类
# ---------------------------------------------------------------------------

@dataclass
class LLMProvider:
    """单个 LLM 供应商的配置信息。

    三个必填字段:
        type:   供应商类型，如 "openai" / "ollama" / "deepseek"
        base_url: API 基础地址
        api_key: 认证密钥
        model:   模型名称
    """
    type: str
    base_url: str
    api_key: str
    model: str


@dataclass
class EmbedProvider:
    """单个 Embedding（向量嵌入）供应商的配置信息。

    相比 LLMProvider 多了 dims 字段，用于声明该模型产出的向量维度，
    校验时会和对端 Qdrant 集合的 vector_size 进行匹配。
    """
    type: str
    base_url: str
    api_key: str
    model: str
    dims: int


@dataclass
class LLMConfig:
    """LLM 供应商集合配置，包含默认供应商名和全部供应商字典。"""
    default: str  # 默认供应商名称
    providers: dict[str, LLMProvider] = field(default_factory=dict)  # name -> LLMProvider

    def get(self, name: str = "") -> LLMProvider:
        """按名称获取 LLM 供应商，name 为空时使用默认供应商。"""
        key = name or self.default
        if key not in self.providers:
            raise KeyError(f"llm provider '{key}' not found")
        return self.providers[key]


@dataclass
class EmbedConfig:
    """Embedding 供应商集合配置，与 LLMConfig 结构对称。"""
    default: str
    providers: dict[str, EmbedProvider] = field(default_factory=dict)

    def get(self, name: str = "") -> EmbedProvider:
        """按名称获取 Embedding 供应商，name 为空时使用默认供应商。"""
        key = name or self.default
        if key not in self.providers:
            raise KeyError(f"embed provider '{key}' not found")
        return self.providers[key]


@dataclass
class SummaryConfig:
    """对话摘要压缩配置，用于会话上下文过长时调用 LLM 做摘要。

    system_prompt 中的 {max_words} 会被替换为 compress_max_words 的值。
    """
    base_url: str = ""
    api_key: str = ""
    model: str = ""
    system_prompt: str = (
        "请将以下对话压缩为{max_words}字以内的摘要，"
        "保留关键信息、用户意图和已确认的事实。"
    )


@dataclass
class SessionConfig:
    """会话管理配置。

    关键字段:
        store:             会话存储后端，支持 "memory" / "redis"
        max_age:           会话最大空闲时间（秒）
        max_turns:         单会话最大轮次数，None 表示不限制
        max_chars:         单会话最大字符数，None 表示不限制
        keep:              触发压缩时保留最近 N 轮
        compress_max_words: 摘要压缩的目标字数
        cleanup_interval:  后台清理间隔（秒）
        memory_max_sessions: 内存后端最多缓存的会话数
        redis_url/prefix:  Redis 后端连接参数
    """
    store: str = "memory"
    max_age: int = 3600
    max_turns: None | int = None
    max_chars: None | int = None
    keep: int = 20
    compress_max_words: int = 1000
    cleanup_interval: int = 300
    memory_max_sessions: int = 2000
    redis_url: str = "redis://localhost:6379/0"
    redis_prefix: str = "kf:sess:"
    summary: SummaryConfig = field(default_factory=SummaryConfig)


@dataclass
class AuthConfig:
    """API 认证配置，基于静态 API Key 白名单的简单鉴权。

    api_keys:   有效的 API Key 列表
    skip_paths: 放行路径前缀列表，这些路径不校验 API Key
    """
    api_keys: list[str] = field(default_factory=list)
    skip_paths: list[str] = field(default_factory=list)


@dataclass
class FileLogConfig:
    enabled: bool = False
    dir: str = "logs"
    rotation: str = "daily"
    keep: int = 7


@dataclass
class LoggingConfig:
    """日志配置，控制日志级别、格式、输出目标和文件存储。"""
    level: str = "INFO"
    format: str = "json"
    output: str = "stdout"
    file: FileLogConfig = field(default_factory=FileLogConfig)


@dataclass
class GuiConfig:
    """GUI（Streamlit）配置。"""
    api_url: str = "http://localhost:9000"


@dataclass
class AppConfig:
    """应用根配置 —— 聚合所有子模块配置。

    工作流/节点:
        workflows: {workflow_name -> workflow_dict}，包含 name / depends_on / collections 等
        nodes:     {"产品名:节点名" -> node_dict}，节点级的 type / params / depends_on 等
    """
    workflows: dict[str, dict] = field(default_factory=dict)
    nodes: dict[str, dict] = field(default_factory=dict)
    llm: LLMConfig | None = None
    embed: EmbedConfig | None = None
    session: SessionConfig = field(default_factory=SessionConfig)
    db: DBConfig | None = None
    auth: AuthConfig = field(default_factory=AuthConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)
    gui: GuiConfig = field(default_factory=GuiConfig)

    def llm_provider(self, name: str = "") -> LLMProvider:
        """快捷方法：直接获取 LLMProvider。"""
        if self.llm is None:
            raise RuntimeError("llm config not loaded")
        return self.llm.get(name)

    def embed_provider(self, name: str = "") -> EmbedProvider:
        """快捷方法：直接获取 EmbedProvider。"""
        if self.embed is None:
            raise RuntimeError("embed config not loaded")
        return self.embed.get(name)

    def node_config(self, name: str) -> dict:
        """按 key（格式 "产品名:节点名"）获取节点配置。"""
        cfg = self.nodes.get(name)
        if cfg is None:
            raise KeyError(f"node config '{name}' not found")
        return cfg

    def wf_collections(self, workflow_name: str) -> list[str]:
        """获取某个工作流绑定的 Qdrant 集合列表。"""
        wf = self.workflows.get(workflow_name)
        if wf is None:
            raise KeyError(f"workflow '{workflow_name}' not found")
        return wf.get("collections", ["default"])


# ---------------------------------------------------------------------------
# 公共 API
# ---------------------------------------------------------------------------

def load_app_config(config_dir: str | Path = "config", env_file: str = ".env") -> AppConfig:
    """加载完整应用配置（应用启动时调用一次）。

    加载顺序:
        1. 初始化环境变量 (.env)
        2. 解析顶层配置文件 (llm / embed / session / db / auth / logging)
        3. 扫描 config/workflows/ 下各产品线的 workflow.yaml + nodes/*.yaml
        4. 组装为 AppConfig 实例并缓存为全局单例
    """
    global _APP_CONFIG

    config_dir = Path(config_dir)
    _init_env(env_file)  # 先注入 .env 环境变量

    # ---- 顶层配置文件 ----
    llm = _load_optional_config(config_dir, "llm")
    embed = _load_optional_config(config_dir, "embed")
    session = _load_optional_config(config_dir, "session")
    db = _load_optional_config(config_dir, "db")
    auth = _load_optional_config(config_dir, "auth")
    logging_cfg = _load_optional_config(config_dir, "logging")
    gui = _load_optional_config(config_dir, "gui")

    # ---- 工作流 & 节点扫描 ----
    workflows: dict[str, dict] = {}
    nodes: dict[str, dict] = {}

    base_dir = config_dir / "workflows"
    if base_dir.is_dir():
        for product_dir in sorted(base_dir.iterdir()):
            if not product_dir.is_dir():
                continue
            product_name = product_dir.name  # 产品线名称（目录名）
            wf_file = product_dir / "workflow.yaml"
            if not wf_file.is_file():
                continue

            # 加载工作流定义
            wf_data = _load_yaml(wf_file)
            wf_name = wf_data.get("name", product_name)
            wf_data["_product"] = product_name  # 注入内部字段
            workflows[wf_name] = wf_data

            # 加载该产品线的所有节点配置
            nodes_dir = product_dir / "nodes"
            if nodes_dir.is_dir():
                for yaml_file in sorted(nodes_dir.glob("*.yaml")):
                    data = _load_yaml(yaml_file)
                    node_name = yaml_file.stem  # 节点名 = 文件名（无扩展名）
                    key = f"{product_name}:{node_name}"  # 全局唯一的节点 key
                    nodes[key] = data

    # 组装全局配置单例
    _APP_CONFIG = AppConfig(
        workflows=workflows, nodes=nodes, llm=llm, embed=embed,
        session=session, db=db, auth=auth or AuthConfig(),
        logging=logging_cfg or LoggingConfig(),
        gui=gui or GuiConfig(),
    )
    return _APP_CONFIG


def get_app_config() -> AppConfig:
    """获取已加载的应用配置单例。

    Raises:
        RuntimeError: 如果未先调用 load_app_config()
    """
    if _APP_CONFIG is None:
        raise RuntimeError(
            "app config not loaded — call load_app_config() at startup"
        )
    return _APP_CONFIG


def get_workflow(config_dir: str | Path = "config", name: str = "") -> dict:
    """便捷函数：加载配置并获取指定工作流定义。

    内部会先调用 load_app_config() 确保配置已就绪。

    Raises:
        KeyError: 工作流名称不存在
    """
    from src.config import load_app_config

    cfg = load_app_config(Path(config_dir))
    wf = cfg.workflows.get(name)
    if wf is None:
        raise KeyError(f"workflow '{name}' not found")
    return wf


# ---------------------------------------------------------------------------
# 内部辅助函数
# ---------------------------------------------------------------------------

def _init_env(env_file: str) -> None:
    """尝试加载 .env 文件中的环境变量（依赖 python-dotenv）。

    该调用是尽力而为的：如果 dotenv 未安装，静默跳过。
    """
    try:
        from dotenv import load_dotenv as _load_dotenv

        _load_dotenv(env_file)
    except ImportError:
        pass  # dotenv 非必需依赖


def _resolve_env(obj):
    """递归遍历对象，将字符串中的 ${VAR} 替换为环境变量的值。

    支持类型:
        str:   直接进行正则替换
        dict:  递归处理每个 value
        list:  递归处理每个元素
        其他:   原样返回
    """
    if isinstance(obj, str):
        return _ENV_PATTERN.sub(lambda m: os.environ.get(m.group(1), ""), obj)
    if isinstance(obj, dict):
        return {k: _resolve_env(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_env(v) for v in obj]
    return obj


def _load_yaml(path: Path) -> dict:
    """读取 YAML 文件并通过 _resolve_env 做环境变量插值。"""
    with open(path, encoding="utf-8") as f:
        return _resolve_env(yaml.safe_load(f))


def _load_optional_config(config_dir: Path, name: str):
    """按名称加载可选配置文件，文件不存在时返回 None。

    分发逻辑 —— 根据 name 调用对应的专用加载函数:
        llm     -> _load_llm_config
        embed   -> _load_embed_config
        session -> _load_session_config
        db      -> _load_db_config
        auth    -> _load_auth_config
        logging -> _load_logging_config
    """
    path = config_dir / f"{name}.yaml"
    if not path.is_file():
        return None
    if name == "llm":
        return _load_llm_config(config_dir)
    if name == "embed":
        return _load_embed_config(config_dir)
    if name == "session":
        return _load_session_config(config_dir)
    if name == "db":
        return _load_db_config(config_dir)
    if name == "auth":
        return _load_auth_config(config_dir)
    if name == "logging":
        return _load_logging_config(config_dir)
    if name == "gui":
        return _load_gui_config(config_dir)
    return None


def _load_llm_config(config_dir: Path) -> LLMConfig:
    """解析 config/llm.yaml 为 LLMConfig 对象。"""
    data = _load_yaml(config_dir / "llm.yaml")
    providers = {}
    for name, p in data.get("providers", {}).items():
        providers[name] = LLMProvider(
            type=p["type"],
            base_url=p["base_url"],
            api_key=p.get("api_key", ""),
            model=p.get("model", ""),
        )
    return LLMConfig(default=data.get("default", ""), providers=providers)


def _load_embed_config(config_dir: Path) -> EmbedConfig:
    """解析 config/embed.yaml 为 EmbedConfig 对象。"""
    data = _load_yaml(config_dir / "embed.yaml")
    providers = {}
    for name, p in data.get("providers", {}).items():
        providers[name] = EmbedProvider(
            type=p["type"],
            base_url=p["base_url"],
            api_key=p.get("api_key", ""),
            model=p.get("model", ""),
            dims=p.get("dims", 0),
        )
    return EmbedConfig(default=data.get("default", ""), providers=providers)


def _load_db_config(config_dir: Path) -> DBConfig:
    """解析 config/db.yaml 为 DBConfig 对象（数据库连接池配置）。"""
    data = _load_yaml(config_dir / "db.yaml")
    pools = {}
    for name, p in data.get("pools", {}).items():
        pools[name] = DBPoolConfig(
            type=p["type"],
            host=p.get("host", "localhost"),
            port=p.get("port", 3306 if p.get("type") == "mysql" else 5432),
            user=p.get("user", ""),
            password=p.get("password", ""),
            database=p.get("database", ""),
            pool_size=p.get("pool_size", 5),  # 默认连接池大小
        )
    return DBConfig(default=data.get("default", ""), pools=pools)


def _load_session_config(config_dir: Path) -> SessionConfig:
    """解析 config/session.yaml 为 SessionConfig 对象。"""
    data = _load_yaml(config_dir / "session.yaml")
    summary_data = data.get("summary", {})
    return SessionConfig(
        store=data.get("store", "memory"),
        max_age=data.get("max_age", 3600),
        max_turns=data.get("max_turns"),
        max_chars=data.get("max_chars"),
        keep=data.get("keep", 20),
        compress_max_words=data.get("compress_max_words", 1000),
        cleanup_interval=data.get("cleanup_interval", 300),
        memory_max_sessions=data.get("memory", {}).get("max_sessions", 2000),
        redis_url=data.get("redis", {}).get("url", "redis://localhost:6379/0"),
        redis_prefix=data.get("redis", {}).get("prefix", "kf:sess:"),
        summary=SummaryConfig(
            base_url=summary_data.get("base_url", ""),
            api_key=summary_data.get("api_key", ""),
            model=summary_data.get("model", ""),
            system_prompt=summary_data.get(
                "system_prompt",
                "请将以下对话压缩为{max_words}字以内的摘要，保留关键信息、用户意图和已确认的事实。",
            ),
        ),
    )


def _load_auth_config(config_dir: Path) -> AuthConfig:
    """解析 config/auth.yaml 为 AuthConfig 对象。"""
    data = _load_yaml(config_dir / "auth.yaml")
    return AuthConfig(
        api_keys=data.get("api_keys", []),
        skip_paths=data.get("skip_paths", []),
    )


def _load_logging_config(config_dir: Path) -> LoggingConfig:
    """解析 config/logging.yaml 为 LoggingConfig 对象。"""
    data = _load_yaml(config_dir / "logging.yaml")
    file_data = data.get("file") or {}
    return LoggingConfig(
        level=data.get("level", "INFO"),
        format=data.get("format", "json"),
        output=data.get("output", "stdout"),
        file=FileLogConfig(
            enabled=file_data.get("enabled", False),
            dir=file_data.get("dir", "logs"),
            rotation=file_data.get("rotation", "daily"),
            keep=file_data.get("keep", 7),
        ),
    )


def _load_gui_config(config_dir: Path) -> GuiConfig:
    """解析 config/gui.yaml 为 GuiConfig 对象。"""
    path = config_dir / "gui.yaml"
    if not path.is_file():
        return GuiConfig()
    data = _load_yaml(path)
    return GuiConfig(
        api_url=data.get("api_url", "http://localhost:9000"),
    )
