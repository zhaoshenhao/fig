# AWS EKS K8s Manifests

> 这些清单与 `deployment/k8s-aliyun/` 目录的差异点：
> - 镜像仓库：ECR 替代 ACR
> - 存储类：gp3 EBS 替代 ESSD
> - 配置挂载：EFS CSI PVC 替代 OSS CSI PVC
> - S3 访问：IRSA (serviceAccountName) 替代 OSS AccessKey
> - Ingress：AWS Load Balancer Controller 替代 ALB Ingress Controller

## 快速部署

```bash
export NS="kf-prod"
export AWS_ACCOUNT="123456789012"
export AWS_REGION="us-east-1"
export ECR="${AWS_ACCOUNT}.dkr.ecr.${AWS_REGION}.amazonaws.com"
export API_TAG="v1.0.0"
export EMBED_TAG="v1.0.0"
export DOMAIN="kf.example.com"

# 1. 创建 StorageClass（仅 Qdrant 需要，其他使用 EFS）
kubectl apply -f deployment/k8s-aws/storageclass.yaml

# 2. 创建 Config PVC (EFS)
kubectl apply -f deployment/k8s-aws/config-pvc.yaml

# 3. 部署服务（参考 k8s/ 目录，替换镜像地址为 ECR）
#   - deployment/k8s-aliyun/kf-api/deployment.yaml     → image: ${ECR}/kf-api:${API_TAG}, serviceAccountName: kf-s3-access
#   - deployment/k8s-aliyun/embed/deployment.yaml      → image: ${ECR}/kf-embed:${EMBED_TAG}
#   - deployment/k8s-aliyun/qdrant/statefulset.yaml    → storageClassName: qdrant-storage

# 4. 部署 Ingress
cat deployment/k8s-aws/ingress.yaml | sed "s|<DOMAIN>|${DOMAIN}|g" | kubectl apply -f -
```

## 参考

完整部署步骤见 `docs/deployments/deployment_CN.md` 场景 D。
