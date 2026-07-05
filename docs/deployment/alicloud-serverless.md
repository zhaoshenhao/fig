# 阿里云 ACK Serverless (ASK) 部署分析

## 背景

曾评估 ACK Serverless 作为替代方案。最终选用标准 ACK 托管版 K8s，本文档保留分析作为参考。

## ECI vs ACK Serverless 对比

| 维度 | ECI | ACK Serverless |
|------|-----|---------------|
| 定义 | 弹性容器实例，裸容器运行 | 基于 K8s API 的 Serverless 集群 |
| 底层 | 安全沙箱（Kata Containers） | ECI（底层相同） |
| K8s 兼容 | 无 K8s API | 完整 K8s 兼容 |
| 计费 | 按 Pod 资源按秒 | 同 ECI，集群管理费目前免费 |
| 管理 | 直接管理容器 | kubectl / Helm / K8s YAML |

## ASK vs ACK 托管版 决策

| 维度 | ACK Serverless | ACK 托管版（当前选择） |
|------|:-:|:-:|
| 节点管理 | 无节点 | 管理 ECS 节点池 |
| 弹性 | Pod 秒级弹性 | HPA + Cluster Autoscaler |
| 持久存储 | ESSD / NAS 均可 | 更灵活（支持本地盘、NVMe） |
| Qdrant 部署 | StatefulSet + ESSD | StatefulSet + ESSD 或本地 NVMe |
| Ingress | ALB Ingress（原生） | Nginx / ALB 均可 |
| 成本 | 按 Pod 资源按秒 | 按 ECS 规格按月 |
| 适用场景 | 波峰波谷明显、短期任务 | 稳定运行、需要全 K8s 能力 |

## 结论

生产环境选用 ACK 托管版理由：
1. 已有现有 ACK 集群，复用现有基础设施
2. Qdrant 等有状态服务更适合标准 K8s StatefulSet
3. 部署 YAML 与标准 K8s 完全一致，无 ECI 兼容限制
4. 多 Worker API 共享 Qdrant，标准 K8s Service Discovery 更稳定
