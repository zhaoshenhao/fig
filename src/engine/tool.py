"""
工具注册表模块 (ToolRegistry)

负责管理工作流引擎中所有可用工具的注册和查找。

ToolRegistry 是一个简单的工具注册表容器，提供以下功能：
- 工具注册：通过名称注册工具函数（Callable）
- 工具查找：通过名称查找已注册的工具函数
- 工具列表：获取所有已注册工具的名称到函数的映射

使用方式：
    registry = ToolRegistry()
    registry.register("rag_search", rag_search)
    fn = registry.get("rag_search")
    if fn:
        result = fn(config, session)

在工作流引擎中的角色：
    引擎在执行每个 DAG 节点时，通过 ToolRegistry 查找节点类型对应的
    工具函数，然后传入节点配置和当前会话数据执行该函数。
"""

from collections.abc import Callable


class ToolRegistry:
    """
    工作流工具注册表。

    管理和维护所有可用的工作流工具函数。每个工具以名称（字符串）为键，
    对应的函数（Callable）为值存储在内部字典中。

    该注册表的生命周期贯穿整个引擎运行过程：
    1. 引擎启动时注册所有内置工具
    2. 用户可通过 register() 方法注册自定义工具
    3. DAG 执行时通过 get() 查找并调用对应工具

    Attributes:
        _tools (dict[str, Callable]): 内部存储，键为工具名称，值为工具函数
    """

    def __init__(self):
        """
        初始化一个空的工具注册表。

        内部 _tools 字典初始为空，后续通过 register() 方法添加工具。
        """
        self._tools: dict[str, Callable] = {}

    def register(self, name: str, fn: Callable):
        """
        注册一个工具函数到注册表中。

        如果同名的工具已经存在，新注册的函数会覆盖旧函数（后注册覆盖先注册）。

        Args:
            name (str): 工具名称，用于后续查找和 DAG 节点类型匹配
            fn (Callable): 工具函数，签名为 fn(config: dict, session) -> dict 或返回其他类型
        """
        self._tools[name] = fn

    def get(self, name: str) -> Callable | None:
        """
        根据名称查找已注册的工具函数。

        Args:
            name (str): 要查找的工具名称

        Returns:
            Callable | None: 如果找到则返回对应的工具函数，否则返回 None。
            返回 None 时表示该工具未注册，调用方应进行错误处理。
        """
        return self._tools.get(name)

    def tools(self) -> dict:
        """
        获取所有已注册工具的副本。

        返回的是内部字典的浅拷贝，因此修改返回的字典不会影响注册表内部状态。

        Returns:
            dict[str, Callable]: 工具名称到工具函数的映射副本
        """
        return dict(self._tools)
