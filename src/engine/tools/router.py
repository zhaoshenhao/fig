"""
条件路由工具模块 (Router)

负责根据上游节点的输出数据动态决定工作流的下一个分支（DAG 条件跳转）。

工作方式：
1. 从会话中获取最近一个节点的输出数据
2. 根据配置的路由规则匹配数据字段的值
3. 返回匹配的分支名称，供工作流引擎决定后续节点的执行路径

支持的匹配模式：
    - exact: 精确匹配（忽略大小写和前后空白）
    - contains: 包含匹配（目标字符串是否出现在字段值中）
    - startswith: 前缀匹配（字段值是否以目标字符串开头）

典型配置结构（config dict）：
    {
        "router": {
            "match_field": "text",      # 要匹配的字段名，默认为 "text"
            "default": "",              # 无匹配时的默认分支名
            "rules": [
                {
                    "match": "exact",   # 匹配模式：exact | contains | startswith
                    "value": "退款",    # 目标值
                    "branch": "refund"  # 跳转到的分支名称
                }
            ]
        }
    }
"""


def router(config: dict, session: dict) -> str:
    """
    执行条件路由决策，返回下游分支名称。

    流程：
    1. 从 config["router"] 中提取路由配置（匹配字段、默认分支、规则列表）
    2. 从会话中取出最近一个节点的输出数据
    3. 逐一检查每条规则，如果匹配成功则返回该规则指定的分支名
    4. 所有规则都不匹配时返回默认分支名

    Args:
        config (dict): 节点配置字典，必须包含 "router" 键，其值为路由配置对象：
            - match_field (str, 可选): 要匹配的数据字段名，默认 "text"
            - default (str, 可选): 默认分支名，无匹配时使用
            - rules (list[dict]): 路由规则列表，每条规则包含：
                - value (str): 用于匹配的目标值
                - match (str): 匹配模式，可选 "exact" / "contains" / "startswith"
                - branch (str): 匹配成功时跳转的分支名
        session (dict): 会话状态字典，必须包含 "nodes" 列表，
            每个 node 包含 "data" 字段（dict）

    Returns:
        str: 下一跳的目标分支名称（由匹配到的规则或默认值决定）
    """
    # 提取路由配置
    rules = config.get("router", {})
    match_field = rules.get("match_field", "text")
    default = rules.get("default", "")

    # 从最近一个执行过的节点中获取输出数据
    # _last_data 逆序遍历 nodes 列表，取第一个节点的 data
    data = _last_data(session)
    # 获取要匹配的字段值，不存在则返回空字符串
    value = data.get(match_field, "")

    # 遍历路由规则，第一个匹配到的规则决定分支走向
    for rule in rules.get("rules", []):
        target = rule.get("value", "")
        match_mode = rule.get("match", "exact")

        if _match(value, target, match_mode):
            return rule.get("branch", default)

    # 所有规则都不匹配，返回默认分支
    return default


def _last_data(session: dict) -> dict:
    """
    从会话节点列表中获取最近一个节点的输出数据。

    逆序遍历 session["nodes"]，返回第一个节点的 "data" 字段。
    用于路由决策时获取最近的可匹配数据。

    Args:
        session (dict): 会话状态字典，必须包含 "nodes" 列表

    Returns:
        dict: 最近一个节点的 data 字典，如果没有节点则返回空字典 {}
    """
    for node in reversed(session["nodes"]):
        return node["data"]
    return {}


def _match(value: str, target: str, mode: str) -> bool:
    """
    根据指定模式判断字段值是否匹配目标值。

    边界情况处理：
        - 所有比较前都会对 value 做 strip() 处理，去除前后空白
        - exact 模式下同时对 value 和 target 做 strip().lower()，忽略大小写和空白
        - 空字符串与空字符串在 exact 模式下会匹配成功

    Args:
        value (str): 待匹配的字段值（来自节点输出数据）
        target (str): 匹配目标值（来自路由规则配置）
        mode (str): 匹配模式，可选 "exact" / "contains" / "startswith"

    Returns:
        bool: 是否匹配成功
    """
    if mode == "exact":
        # 精确匹配：忽略大小写和前后空白
        return value.strip().lower() == target.strip().lower()
    if mode == "contains":
        # 包含匹配：target 是否作为子串出现在 value 中（忽略大小写）
        return target.lower() in value.lower()
    if mode == "startswith":
        # 前缀匹配：value（去除空白后）是否以 target 开头（忽略大小写）
        return value.strip().lower().startswith(target.lower())
    # 未知的匹配模式，保守返回 False（不匹配）
    return False
