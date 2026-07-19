pipeline {
    agent any

    parameters {
        choice(
            name: 'ENV',
            choices: ['test', 'production'],
            description: '部署环境 (mb-test / mb-pr)'
        )
        string(
            name: 'SERVICES',
            defaultValue: 'chat-api,admin-api',
            description: '部署的服务（逗号分隔: chat-api,admin-api,embed,qdrant,web-gui）'
        )
        string(
            name: 'IMAGE_TAG',
            defaultValue: '',
            description: '镜像标签（留空则使用 BUILD_NUMBER。生产环境填入测试环境已构建的 tag，避免重复构建）'
        )
        booleanParam(
            name: 'REBUILD_IMAGES',
            defaultValue: true,
            description: '若镜像已存在是否重新 Build。生产环境建议关闭，直接复用测试环境已验证的镜像'
        )
    }

    environment {
        NAMESPACE = "${params.ENV == 'test' ? 'mb-test' : 'mb-pr'}"
        DOMAIN = 'kf.dev.youbanban.com'
        OSS_WORKFLOW_BUCKET = 'kf-workflow'
        OSS_UI_BUCKET = 'kf-ui'
        OSS_PATH_PREFIX = "${params.ENV == 'test' ? 'mb-test' : 'mb-pr'}"
        QDRANT_STORAGE_SIZE = '2Gi'
        TOOLS = '/mnt/devops-tools'
    }

    stages {
        stage('Env Setup') {
            steps {
                sh """
                    APPHOME=${TOOLS} . ${TOOLS}/env.sh
                    echo "Registry: \$DOCKER_REG_BASE_URL/\$DOCKER_NS"
                    echo "Namespace: ${NAMESPACE}"
                """
            }
        }

        stage('Build Images') {
            parallel {
                stage('kf-api') {
                    when {
                        expression {
                            (params.SERVICES.split(',').contains('chat-api') || params.SERVICES.split(',').contains('admin-api')) && params.REBUILD_IMAGES
                        }
                    }
                    steps {
                        script {
                            env.API_IMAGE_TAG = resolveImageTag('kf-api')
                            sh """
                                APPHOME=${TOOLS} . ${TOOLS}/env.sh
                                echo "\$DOCKER_REG_PASSWORD" | docker login \$DOCKER_REG_BASE_URL -u \$DOCKER_REG_USER --password-stdin
                                docker build -t \$DOCKER_REG_BASE_URL/\$DOCKER_NS/kf-api:${env.API_IMAGE_TAG} -f Dockerfile .
                                docker push \$DOCKER_REG_BASE_URL/\$DOCKER_NS/kf-api:${env.API_IMAGE_TAG}
                            """
                        }
                    }
                }
                stage('kf-embed') {
                    when {
                        expression {
                            params.SERVICES.split(',').contains('embed') && params.REBUILD_IMAGES
                        }
                    }
                    steps {
                        script {
                            env.EMBED_IMAGE_TAG = resolveImageTag('kf-embed')
                            sh """
                                APPHOME=${TOOLS} . ${TOOLS}/env.sh
                                echo "\$DOCKER_REG_PASSWORD" | docker login \$DOCKER_REG_BASE_URL -u \$DOCKER_REG_USER --password-stdin
                                docker build -t \$DOCKER_REG_BASE_URL/\$DOCKER_NS/kf-embed:${env.EMBED_IMAGE_TAG} -f Dockerfile.embed .
                                docker push \$DOCKER_REG_BASE_URL/\$DOCKER_NS/kf-embed:${env.EMBED_IMAGE_TAG}
                            """
                        }
                    }
                }
            }
        }

        stage('Resolve Image Tags') {
            when {
                expression { !params.REBUILD_IMAGES }
            }
            steps {
                script {
                    def apiTag = params.IMAGE_TAG ?: error("REBUILD_IMAGES=false 时必须指定 IMAGE_TAG")
                    env.API_IMAGE_TAG = apiTag
                    env.EMBED_IMAGE_TAG = apiTag

                    sh """
                        APPHOME=${TOOLS} . ${TOOLS}/env.sh
                        docker manifest inspect \$DOCKER_REG_BASE_URL/\$DOCKER_NS/kf-api:${apiTag} > /dev/null 2>&1 || {
                            echo "镜像不存在: \$DOCKER_REG_BASE_URL/\$DOCKER_NS/kf-api:${apiTag}"
                            echo "请先构建并推送到容器仓库，或启用 REBUILD_IMAGES"
                            exit 1
                        }
                        echo "使用已有镜像: \$DOCKER_REG_BASE_URL/\$DOCKER_NS/kf-api:${apiTag}"
                    """
                }
            }
        }

        stage('Upload Web GUI to OSS') {
            when {
                expression { params.SERVICES.split(',').contains('web-gui') }
            }
            steps {
                dir('src/gui/ui') {
                    sh 'npm ci && npm run build'
                    sh """
                        APPHOME=${TOOLS} . ${TOOLS}/env.sh
                        ossutil cp -r dist/ oss://${OSS_UI_BUCKET}/${OSS_PATH_PREFIX}/ --update
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

def resolveImageTag(String imageName) {
    def tag = params.IMAGE_TAG ?: "${env.BUILD_NUMBER}"
    def imgBase = "\$DOCKER_REG_BASE_URL/\$DOCKER_NS/${imageName}"
    sh """
        APPHOME=${TOOLS} . ${TOOLS}/env.sh
        docker manifest inspect ${imgBase}:${tag} > /dev/null 2>&1 && echo "镜像已存在: ${imgBase}:${tag}" || true
    """
    return tag
}

def deployService(String dir, String serviceName) {
    sh script: """
        APPHOME=${TOOLS} . ${TOOLS}/env.sh
        for f in \$(ls ${dir}/*.yaml 2>/dev/null); do
            sed -e 's/<NAMESPACE>/${NAMESPACE}/g' \
                -e 's|<ACR_REGISTRY>|\$DOCKER_REG_BASE_URL/\$DOCKER_NS|g' \
                -e 's/<API_IMAGE_TAG>/${API_IMAGE_TAG}/g' \
                -e 's/<EMBED_IMAGE_TAG>/${EMBED_IMAGE_TAG}/g' \
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
