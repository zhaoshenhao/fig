pipeline {
    agent any

    parameters {
        choice(
            name: 'ENV',
            choices: ['test', 'production'],
            description: '部署环境 (mb-test / mb-pr)'
        )
        string(
            name: 'IMAGE_TAG',
            defaultValue: '',
            description: '镜像标签（必填，由 kf-build 构建输出版本号）'
        )
        string(
            name: 'SERVICES',
            defaultValue: 'chat-api,admin-api,embed,qdrant',
            description: '部署的服务（逗号分隔: chat-api,admin-api,embed,qdrant）'
        )
    }

    environment {
        NAMESPACE = "${params.ENV == 'test' ? 'mb-test' : 'mb-pr'}"
        DOMAIN = 'kf.dev.youbanban.com'
        QDRANT_STORAGE_SIZE = '2Gi'
        TOOLS = '/mnt/devops-tools'
        KUBECONFIG = '/mnt/kubeconf/config'
    }

    stages {
        stage('Validate Image Tag') {
            steps {
                script {
                    if (!params.IMAGE_TAG) {
                        error("IMAGE_TAG 不能为空，请填入 kf-build 构建的版本号")
                    }
                    sh """
                        APPHOME=${TOOLS} . ${TOOLS}/env.sh
                        docker manifest inspect \$DOCKER_REG_BASE_URL/\$DOCKER_NS/kf-api:${params.IMAGE_TAG} > /dev/null 2>&1 || {
                            echo "镜像不存在: \$DOCKER_REG_BASE_URL/\$DOCKER_NS/kf-api:${params.IMAGE_TAG}"
                            echo "请先运行 kf-build 构建此版本"
                            exit 1
                        }
                        echo "使用镜像标签: ${params.IMAGE_TAG}"
                    """
                }
            }
        }

        stage('Deploy to K8s') {
            parallel {
                stage('chat-api') {
                    when {
                        expression { params.SERVICES.split(',').contains('chat-api') }
                    }
                    steps {
                        deployService('deployment/k8s-aliyun/chat-api', 'chat-api')
                    }
                }
                stage('admin-api') {
                    when {
                        expression { params.SERVICES.split(',').contains('admin-api') }
                    }
                    steps {
                        deployService('deployment/k8s-aliyun/admin-api', 'admin-api')
                    }
                }
                stage('embed') {
                    when {
                        expression { params.SERVICES.split(',').contains('embed') }
                    }
                    steps {
                        deployService('deployment/k8s-aliyun/embed', 'embed')
                    }
                }
                stage('qdrant') {
                    when {
                        expression { params.SERVICES.split(',').contains('qdrant') }
                    }
                    steps {
                        deployService('deployment/k8s-aliyun/qdrant', 'qdrant')
                    }
                }
                stage('global') {
                    steps {
                        script {
                            def globalFiles = [
                                'deployment/k8s-aliyun/namespace.yaml',
                                'deployment/k8s-aliyun/ingress.yaml',
                            ]
                            for (f in globalFiles) {
                                sh """
                                    APPHOME=${TOOLS} . ${TOOLS}/env.sh
                                    cat ${f} | sed 's/<NAMESPACE>/${NAMESPACE}/g; s/<DOMAIN>/${DOMAIN}/g' | \$KUBECTL apply -f -
                                """
                            }
                        }
                    }
                }
            }
        }

        stage('Health Check') {
            parallel {
                stage('chat-api') {
                    when {
                        expression { params.SERVICES.split(',').contains('chat-api') }
                    }
                    steps {
                        checkHealth('chat-api')
                    }
                }
                stage('admin-api') {
                    when {
                        expression { params.SERVICES.split(',').contains('admin-api') }
                    }
                    steps {
                        checkHealth('admin-api')
                    }
                }
                stage('embed') {
                    when {
                        expression { params.SERVICES.split(',').contains('embed') }
                    }
                    steps {
                        checkHealth('embed')
                    }
                }
                stage('qdrant') {
                    when {
                        expression { params.SERVICES.split(',').contains('qdrant') }
                    }
                    steps {
                        sh """
                            APPHOME=${TOOLS} . ${TOOLS}/env.sh
                            \$KUBECTL wait --for=condition=ready pod -l app=qdrant -n ${NAMESPACE} --timeout=120s
                        """
                    }
                }
            }
        }
    }
}

def deployService(String dir, String serviceName) {
    sh script: """
        APPHOME=${TOOLS} . ${TOOLS}/env.sh
        for f in \$(ls ${dir}/*.yaml 2>/dev/null); do
            sed -e 's/<NAMESPACE>/${NAMESPACE}/g' \
                -e 's|<ACR_REGISTRY>|\$DOCKER_REG_BASE_URL/\$DOCKER_NS|g' \
                -e 's/<API_IMAGE_TAG>/${params.IMAGE_TAG}/g' \
                -e 's/<EMBED_IMAGE_TAG>/${params.IMAGE_TAG}/g' \
                -e 's/<QDRANT_STORAGE_SIZE>/${QDRANT_STORAGE_SIZE}/g' \
                \$f | \$KUBECTL apply -f -
        done
    """
}

def checkHealth(String serviceName) {
    sh """
        APPHOME=${TOOLS} . ${TOOLS}/env.sh
        \$KUBECTL wait --for=condition=ready pod -l app=${serviceName} -n ${NAMESPACE} --timeout=120s
        POD=\$(\$KUBECTL get pods -l app=${serviceName} -n ${NAMESPACE} -o jsonpath='{.items[0].metadata.name}')
        \$KUBECTL exec \$POD -n ${NAMESPACE} -- curl -s http://localhost:8000/health || echo "health check fallback: pod ready"
    """
}
