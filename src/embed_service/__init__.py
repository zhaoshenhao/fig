"""kf-embed —— 轻量 Embedding 微服务。

基于 FastEmbed（Qdrant 官方 ONNX 推理库）提供 OpenAI 兼容的
`/v1/embeddings` 接口，替代独立的 Ollama 容器承担向量化职责。

模块划分:
    service —— 模型加载与推理封装（懒加载单例 + 线程锁）
    app     —— FastAPI 应用（/v1/embeddings, /health, /ready）
"""
