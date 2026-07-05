"""
并行分支合并工具模块 (Merge)

负责在工作流 DAG 中合并多个并行分支的节点执行结果。
当工作流通过 Router 节点分叉为多个并行分支后，Merge 工具将所有分支的节点
按时间顺序合并回主执行序列中。

工作方式：
1. 接收 switch 节点（分叉点）的索引和各分支的节点列表
2. 为每个分支节点标记其来源分支名（_branch 字段）并建立父子关系（pre 字段）
3. 按时间戳排序所有分支节点，追加到 session["nodes"] 末尾
4. 在 switch 节点上记录各分支的起止索引范围（branches 字段）

典型使用场景：
    ```
    Router → [BranchA, BranchB] → Merge → 后续节点
    ```
"""


def merge_branches(
    session: dict,
    switch_node_index: int,
    branches: dict[str, list[dict]],
) -> None:
    """
    将多个并行分支的节点合并到会话的执行序列中。

    流程：
    1. 获取 switch 节点（分叉点）的名称
    2. 遍历所有分支节点：如果节点的 pre 字段为空，设置为 switch 节点名
    3. 为每个节点添加 _branch 标记（标识来源分支）
    4. 按 timestamp 排序所有分支节点
    5. 将所有分支节点追加到 session["nodes"] 末尾
    6. 计算每个分支节点在总序列中的起止索引，记录到 switch 节点的 branches 字段

    Args:
        session (dict): 会话状态字典，必须包含 "nodes" 列表，
            每个 node 包含 name、timestamp、pre、data 等字段
        switch_node_index (int): switch 节点（Router 节点）在 session["nodes"] 中的索引
        branches (dict[str, list[dict]]): 分支名到节点列表的映射，
            例如 {"refund": [node1, node2], "exchange": [node3]}

    Returns:
        None: 直接修改 session 字典
    """
    # 获取 switch 节点（Router 分叉点）的信息
    switch_node = session["nodes"][switch_node_index]
    switch_name = switch_node["name"]

    # 第一步：遍历所有分支节点，标记来源分支并处理前置节点关系
    all_branch_nodes: list[dict] = []
    for branch_name, branch_nodes in branches.items():
        for node in branch_nodes:
            # 如果节点没有前置节点（pre 为空），将 switch 节点设为前置
            # 这确保了分支上的第一个节点正确地 follow switch 节点
            if node["pre"] == "":
                node["pre"] = switch_name
            # 标记节点来源分支，后续用于识别和查找
            node["_branch"] = branch_name
            all_branch_nodes.append(node)

    # 第二步：按时间戳排序所有分支节点
    # 这确保了不同分支的节点按实际执行时间交错排列，保持全局时序
    all_branch_nodes.sort(key=lambda n: n["timestamp"])

    # 第三步：计算追加到 session["nodes"] 后的起始索引
    actual_start = len(session["nodes"])
    # 将所有分支节点追加到节点列表末尾
    session["nodes"].extend(all_branch_nodes)

    # 第四步：计算每个分支在总序列中的起止索引范围
    # branch_index 结构: {"branch_name": {"start": 起始索引, "end": 结束索引}}
    # start 是分支第一个节点在 session["nodes"] 中的索引
    # end 是分支最后一个节点之后的位置（可用于切片：nodes[start:end]）
    branch_index: dict[str, dict] = {}
    for name in branches:
        branch_index[name] = {"start": actual_start, "end": actual_start}

    for i, node in enumerate(all_branch_nodes):
        idx = actual_start + i  # 该节点在 session["nodes"] 中的全局索引
        name = node["_branch"]

        if branch_index[name]["start"] == actual_start:
            # 第一次遇到该分支的节点：设置 start 为当前索引
            branch_index[name] = {"start": idx, "end": idx + 1}
        else:
            # 后续节点：扩展 end 到当前索引 + 1
            branch_index[name]["end"] = idx + 1

    # 第五步：在 switch 节点上记录分支索引信息
    # 下游节点可以通过 switch_node["branches"] 了解各分支的节点范围
    switch_node["branches"] = branch_index
