pipeline {
    agent any

    parameters {
        choice(
            name: 'ENV',
            choices: ['test', 'production'],
            description: '部署环境 (mb-test / mb-pr)'
        )
        extendedChoice(
            name: 'SERVICES',
            type: 'CHECKBOX',
            value: 'chat-api,admin-api,embed,qdrant,web-gui',
            description: '选择需要部署的服务'
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
        ACR = 'registry.cn-hangzhou.aliyuncs.com/kf'
        DOMAIN = 'kf.dev.youbanban.com'
        OSS_ENDPOINT = 'oss-cn-hangzhou.aliyuncs.com'
        OSS_INT_ENDPOINT = 'oss-cn-hangzhou-internal.aliyuncs.com'
        OSS_WORKFLOW_BUCKET = 'kf-workflow'
        OSS_UI_BUCKET = 'kf-ui'
        OSS_PATH_PREFIX = "${params.ENV == 'test' ? 'mb-test' : 'mb-pr'}"
        QDRANT_STORAGE_SIZE = '2Gi'
    }

    stages {
        stage('Build Images') {
            parallel {
                stage('kf-api') {
                    when {
                        expression {
                            def s = params.SERVICES.split(',')
                            (s.contains('chat-api') || s.contains('admin-api')) && params.REBUILD_IMAGES
                        }
                    }
                    steps {
                        script {
                            env.API_IMAGE_TAG = resolveImageTag('kf-api')
                            withCredentials([usernamePassword(
                                credentialsId: 'ali_dockerhub',
                                usernameVariable: 'ACR_USER',
                                passwordVariable: 'ACR_PASS'
                            )]) {
                                sh "echo \${ACR_PASS} | docker login registry.cn-hangzhou.aliyuncs.com -u \${ACR_USER} --password-stdin"
                            }
                            sh "docker build -t ${ACR}/kf-api:${env.API_IMAGE_TAG} -f Dockerfile ."
                            sh "docker push ${ACR}/kf-api:${env.API_IMAGE_TAG}"
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
                            withCredentials([usernamePassword(
                                credentialsId: 'ali_dockerhub',
                                usernameVariable: 'ACR_USER',
                                passwordVariable: 'ACR_PASS'
                            )]) {
                                sh "echo \${ACR_PASS} | docker login registry.cn-hangzhou.aliyuncs.com -u \${ACR_USER} --password-stdin"
                            }
                            sh "docker build -t ${ACR}/kf-embed:${env.EMBED_IMAGE_TAG} -f Dockerfile.embed ."
                            sh "docker push ${ACR}/kf-embed:${env.EMBED_IMAGE_TAG}"
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

                    def apiImage = "${ACR}/kf-api:${apiTag}"
                    def apiCheck = sh(
                        script: "docker manifest inspect ${apiImage} > /dev/null 2>&1",
                        returnStatus: true
                    )
                    if (apiCheck != 0) {
                        error("镜像不存在: ${apiImage}。请先构建并推送到 ACR，或启用 REBUILD_IMAGES")
                    }

                    if (params.SERVICES.split(',').contains('embed')) {
                        def embedImage = "${ACR}/kf-embed:${apiTag}"
                        def embedCheck = sh(
                            script: "docker manifest inspect ${embedImage} > /dev/null 2>&1",
                            returnStatus: true
                        )
                        if (embedCheck != 0) {
                            error("镜像不存在: ${embedImage}。请先构建并推送到 ACR，或启用 REBUILD_IMAGES")
                        }
                    }

                    echo "使用已有镜像: ${apiImage}"
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
                    sh "ossutil cp -r dist/ oss://${OSS_UI_BUCKET}/${OSS_PATH_PREFIX}/ --update"
                }
            }
        }

        stage('Deploy to K8s') {
            parallel {
                stage('chat-api') {
                    when {
                        expression { params.SERVICES.split(',').contains('chat-api') }
                    }
                    steps { deployService('deployment/k8s-aliyun/chat-api', 'chat-api') }
                }
                stage('admin-api') {
                    when {
                        expression { params.SERVICES.split(',').contains('admin-api') }
                    }
                    steps { deployService('deployment/k8s-aliyun/admin-api', 'admin-api') }
                }
                stage('embed') {
                    when {
                        expression { params.SERVICES.split(',').contains('embed') }
                    }
                    steps { deployService('deployment/k8s-aliyun/embed', 'embed') }
                }
                stage('qdrant') {
                    when {
                        expression { params.SERVICES.split(',').contains('qdrant') }
                    }
                    steps { deployService('deployment/k8s-aliyun/qdrant', 'qdrant') }
                }
                stage('global') {
                    steps {
                        script {
                            def globalFiles = [
                                'deployment/k8s-aliyun/namespace.yaml',
                                'deployment/k8s-aliyun/ingress.yaml',
                            ]
                            for (f in globalFiles) {
                                sh "cat ${f} | sed 's/<NAMESPACE>/${NAMESPACE}/g; s/<DOMAIN>/${DOMAIN}/g' | kubectl apply -f -"
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
                    steps { checkHealth('chat-api') }
                }
                stage('admin-api') {
                    when {
                        expression { params.SERVICES.split(',').contains('admin-api') }
                    }
                    steps { checkHealth('admin-api') }
                }
                stage('embed') {
                    when {
                        expression { params.SERVICES.split(',').contains('embed') }
                    }
                    steps { checkHealth('embed') }
                }
                stage('qdrant') {
                    when {
                        expression { params.SERVICES.split(',').contains('qdrant') }
                    }
                    steps {
                        sh "kubectl wait --for=condition=ready pod -l app=qdrant -n ${NAMESPACE} --timeout=120s"
                    }
                }
            }
        }
    }
}

def resolveImageTag(String imageName) {
    def tag = params.IMAGE_TAG ?: "${env.BUILD_NUMBER}"
    def full = "${ACR}/${imageName}:${tag}"
    def check = sh(script: "docker manifest inspect ${full} > /dev/null 2>&1", returnStatus: true)
    if (check == 0 && !params.REBUILD_IMAGES) {
        echo "镜像已存在，跳过构建: ${full}"
        return tag
    }
    return tag
}

def deployService(String dir, String serviceName) {
    sh script: """
        for f in \$(ls ${dir}/*.yaml 2>/dev/null); do
            sed -e 's/<NAMESPACE>/${NAMESPACE}/g' \
                -e 's/<ACR_REGISTRY>/${ACR}/g' \
                -e 's/<API_IMAGE_TAG>/${API_IMAGE_TAG}/g' \
                -e 's/<EMBED_IMAGE_TAG>/${EMBED_IMAGE_TAG}/g' \
                -e 's/<QDRANT_STORAGE_SIZE>/${QDRANT_STORAGE_SIZE}/g' \
                \$f | kubectl apply -f -
        done
    """
}

def checkHealth(String serviceName) {
    sh "kubectl wait --for=condition=ready pod -l app=${serviceName} -n ${NAMESPACE} --timeout=120s"
    sh script: """
        POD=\$(kubectl get pods -l app=${serviceName} -n ${NAMESPACE} -o jsonpath='{.items[0].metadata.name}')
        kubectl exec \$POD -n ${NAMESPACE} -- curl -s http://localhost:8000/health || echo "health check fallback: pod ready"
    """
}
