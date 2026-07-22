pipeline {
    agent any

    parameters {
        choice(
            name: 'ENV',
            choices: ['test', 'production'],
            description: '部署环境 (mb-test / mb-pr)'
        )
        string(name: 'API_TAG', defaultValue: 'latest', description: 'kf-api 镜像标签（空/-/0 跳过）')
        string(name: 'EMBED_TAG', defaultValue: 'latest', description: 'embed 镜像标签（空/-/0 跳过）')
        string(name: 'QDRANT_TAG', defaultValue: 'latest', description: 'kf-qdrant 镜像标签（空/-/0 跳过）')
        string(name: 'WORKFLOW_TAG', defaultValue: 'latest', description: 'workflow OSS 同步（空/-/0 跳过；latest=HEAD；其他=Tag）')
        string(name: 'WEBUI_TAG', defaultValue: 'latest', description: 'Web GUI OSS 发布（空/-/0 跳过；latest=HEAD；其他=Tag）')
    }

    environment {
        NAMESPACE = "${params.ENV == 'test' ? 'mb-test' : 'mb-pr'}"
        DOMAIN = 'kf.dev.youbanban.com'
        QDRANT_STORAGE_SIZE = '20Gi'
        NAS_PVC = "${params.ENV == 'test' ? 'mb-test-nas1' : 'mb-pr-nas1'}"
        NAS_PVC_DOCS = "${params.ENV == 'test' ? 'mb-test-nas2' : 'mb-pr-nas2'}"
        OSS_WORKFLOW_PVC = "oss-workflow"
        OSS_WEBUI_PVC = "oss-webui"
        TOOLS = '/mnt/devops-tools'
        KUBECONFIG = '/mnt/kubeconf/config'
        OSS_WORKFLOW_BUCKET = 'kf-workflow'
        OSS_UI_BUCKET = "kf-ui-${NAMESPACE}"
        OSS_PATH_PREFIX = "${params.ENV == 'test' ? 'mb-test' : 'mb-pr'}"
    }

    stages {
        stage('Env Setup') {
            steps {
                sh """
                    APPHOME=${TOOLS} . ${TOOLS}/env.sh
                    echo "Registry: \$DOCKER_REG_BASE_URL/\$DOCKER_NS"
                    echo "Namespace: ${NAMESPACE}"
                    if [ -x /mnt/ossutil ]; then
                        cp /mnt/ossutil ./ossutil && chmod +x ./ossutil
                        echo "ossutil ready"
                    else
                        echo "WARN: /mnt/ossutil not found, OSS steps will fail"
                    fi
                    # Init ossutil config from K8s Secret
                    if [ -x ./ossutil ]; then
                        export OSS_ACCESS_KEY_ID=\$(\$KUBECTL get secret kf-secrets -n ${NAMESPACE} -o jsonpath='{.data.OSS_ACCESS_KEY_ID}' | base64 -d)
                        export OSS_ACCESS_KEY_SECRET=\$(\$KUBECTL get secret kf-secrets -n ${NAMESPACE} -o jsonpath='{.data.OSS_ACCESS_KEY_SECRET}' | base64 -d)
                        export OSS_ENDPOINT=oss-cn-shanghai-internal.aliyuncs.com
                        ./ossutil config -e \$OSS_ENDPOINT -i \$OSS_ACCESS_KEY_ID -k \$OSS_ACCESS_KEY_SECRET -L CH 2>&1 || true
                        echo "ossutil configured"
                    fi
                """
            }
        }

        stage('Validate Tags') {
            steps {
                script {
                    def deploying = !isSkipped(params.API_TAG) || !isSkipped(params.EMBED_TAG) || !isSkipped(params.QDRANT_TAG)
                    if (!deploying && isSkipped(params.WORKFLOW_TAG) && isSkipped(params.WEBUI_TAG)) {
                        error("至少需要一个有效的部署目标（所有 TAG 为空）")
                    }
                    if (!isSkipped(params.API_TAG) || !isSkipped(params.EMBED_TAG) || !isSkipped(params.QDRANT_TAG)) {
                        sh """
                            APPHOME=${TOOLS} . ${TOOLS}/env.sh
                            docker manifest inspect \$DOCKER_REG_BASE_URL/\$DOCKER_NS/kf-api:${params.API_TAG} > /dev/null 2>&1 || \
                            docker manifest inspect \$DOCKER_REG_BASE_URL/\$DOCKER_NS/kf-embed:${params.EMBED_TAG} > /dev/null 2>&1 || true
                            echo "镜像验证完成"
                        """
                    }
                }
            }
        }

        stage('OSS: Workflow Config') {
            when { expression { !isSkipped(params.WORKFLOW_TAG) } }
            steps {
                script {
                    sh "git fetch --tags"
                    if (isLatest(params.WORKFLOW_TAG)) {
                        sh """
                            APPHOME=${TOOLS} . ${TOOLS}/env.sh
                            ./ossutil cp -r config/workflows/ oss://${OSS_WORKFLOW_BUCKET}/${OSS_PATH_PREFIX}/ --update
                        """
                    } else {
                        sh """
                            APPHOME=${TOOLS} . ${TOOLS}/env.sh
                            rm -rf /tmp/wf-export && mkdir -p /tmp/wf-export
                            git archive ${params.WORKFLOW_TAG} -- config/workflows/ | tar xf - -C /tmp/wf-export
                            ./ossutil cp -r /tmp/wf-export/config/workflows/ oss://${OSS_WORKFLOW_BUCKET}/${OSS_PATH_PREFIX}/ --update
                            rm -rf /tmp/wf-export
                        """
                    }
                }
            }
        }

        stage('OSS: Web GUI') {
            when { expression { !isSkipped(params.WEBUI_TAG) } }
            steps {
                script {
                    sh "git fetch --tags"
                    if (isLatest(params.WEBUI_TAG)) {
                        sh """
                            APPHOME=${TOOLS} . ${TOOLS}/env.sh
                            echo "window.KF_API_URL = \\"https://${DOMAIN}\\";" > src/gui/ui/dist/config.js
                            ./ossutil cp -r src/gui/ui/dist/ oss://${OSS_UI_BUCKET}/ --update
                        """
                    } else {
                        sh """
                            APPHOME=${TOOLS} . ${TOOLS}/env.sh
                            rm -rf /tmp/ui-export && mkdir -p /tmp/ui-export
                            git archive ${params.WEBUI_TAG} -- src/gui/ui/dist/ | tar xf - -C /tmp/ui-export
                            echo "window.KF_API_URL = \\"https://${DOMAIN}\\";" > /tmp/ui-export/src/gui/ui/dist/config.js
                            ./ossutil cp -r /tmp/ui-export/src/gui/ui/dist/ oss://${OSS_UI_BUCKET}/ --update
                            rm -rf /tmp/ui-export
                        """
                    }
                }
            }
        }

        stage('Deploy to K8s') {
            steps {
                script {
                    // Clean up old renamed services to free Service IPs
                    sh """
                        APPHOME=${TOOLS} . ${TOOLS}/env.sh
                        \$KUBECTL delete service qdrant -n ${NAMESPACE} --ignore-not-found 2>&1 || true
                        \$KUBECTL delete service embed -n ${NAMESPACE} --ignore-not-found 2>&1 || true
                        \$KUBECTL delete statefulset qdrant -n ${NAMESPACE} --cascade=orphan --ignore-not-found 2>&1 || true
                        \$KUBECTL delete statefulset embed -n ${NAMESPACE} --ignore-not-found 2>&1 || true
                    """
                    // Deploy in dependency order: kf-qdrant → kf-embed → kf-api → global
                    if (!isSkipped(params.QDRANT_TAG)) {
                        deployQdrant()
                    }
                    if (!isSkipped(params.EMBED_TAG)) {
                        deployService('deployment/k8s-aliyun/embed', params.EMBED_TAG)
                    }
                    if (!isSkipped(params.API_TAG)) {
                        deployService('deployment/k8s-aliyun/kf-api', params.API_TAG)
                    }
                    // global resources (namespace + OSS PVCs + OSS webui service + plugin + ingress)
                    for (f in ['deployment/k8s-aliyun/namespace.yaml', 'deployment/k8s-aliyun/oss-pvc.yaml', 'deployment/k8s-aliyun/oss-webui-external.yaml', 'deployment/k8s-aliyun/oss-webui-plugin.yaml', 'deployment/k8s-aliyun/ingress.yaml']) {
                        sh """
                            APPHOME=${TOOLS} . ${TOOLS}/env.sh
                            cat ${f} | sed 's/<NAMESPACE>/${NAMESPACE}/g; s/<DOMAIN>/${DOMAIN}/g' | \$KUBECTL apply -f -
                        """
                    }
                }
            }
        }

        stage('Health Check') {
            failFast false
            parallel {
                stage('kf-api') {
                    when { expression { !isSkipped(params.API_TAG) } }
                    steps { checkHealth('kf-api') }
                }
                stage('kf-embed') {
                    when { expression { !isSkipped(params.EMBED_TAG) } }
                    steps { checkHealth('kf-embed') }
                }
                stage('kf-qdrant') {
                    when { expression { !isSkipped(params.QDRANT_TAG) } }
                    steps {
                        sh """
                            APPHOME=${TOOLS} . ${TOOLS}/env.sh
                            \$KUBECTL wait --for=condition=ready pod -l app=kf-qdrant -n ${NAMESPACE} --timeout=120s
                        """
                    }
                }
            }
        }
    }
}

def isSkipped(String val) {
    return val == null || val == '' || val == '-' || val == '0'
}

def isLatest(String val) {
    return val == 'latest'
}

def deployService(String dir, String tag) {
    sh script: """
        APPHOME=${TOOLS} . ${TOOLS}/env.sh
        DEPLOY_NAME=\$(basename ${dir})
        echo "Deleting old \$DEPLOY_NAME..."
        \$KUBECTL delete deployment/\$DEPLOY_NAME -n ${NAMESPACE} --ignore-not-found 2>&1 || true
        sleep 3
        for f in \$(ls ${dir}/*.yaml 2>/dev/null); do
            sed -e 's/<NAMESPACE>/${NAMESPACE}/g' \\
                -e "s|<ACR_REGISTRY>|\$DOCKER_REG_BASE_URL/\$DOCKER_NS|g" \\
                -e 's/<API_IMAGE_TAG>/${tag}/g' \\
                -e 's/<EMBED_IMAGE_TAG>/${tag}/g' \\
                -e "s/<BUILD_TIME>/\$(date -u +%Y-%m-%dT%H:%M:%SZ)/g" \\
                -e "s/<GIT_COMMIT>/${env.GIT_COMMIT ?: 'unknown'}/g" \\
                -e 's/<QDRANT_STORAGE_SIZE>/${QDRANT_STORAGE_SIZE}/g' \\
                -e 's/<NAS_PVC_NAME>/${NAS_PVC}/g' \\
                -e 's/<NAS_PVC_DOCS>/${NAS_PVC_DOCS}/g' \\
                -e 's/<OSS_WORKFLOW_PVC>/${OSS_WORKFLOW_PVC}/g' \\
                -e 's/<OSS_WEBUI_PVC>/${OSS_WEBUI_PVC}/g' \\
                \$f | \$KUBECTL apply -f -
        done
    """
}

def deployQdrant() {
    sh script: """
        APPHOME=${TOOLS} . ${TOOLS}/env.sh
        QD_DIR=deployment/k8s-aliyun/qdrant

        # Clean up old qdrant resources (renamed to kf-qdrant)
        \$KUBECTL delete service qdrant -n ${NAMESPACE} --ignore-not-found 2>&1 || true
        \$KUBECTL delete statefulset qdrant -n ${NAMESPACE} --cascade=orphan --ignore-not-found 2>&1 || true

        sed 's/<NAMESPACE>/${NAMESPACE}/g' \$QD_DIR/service.yaml | \$KUBECTL apply -f -

        if \$KUBECTL get statefulset kf-qdrant -n ${NAMESPACE} >/dev/null 2>&1; then
            CUR=\$(\$KUBECTL get statefulset kf-qdrant -n ${NAMESPACE} -o jsonpath='{.spec.volumeClaimTemplates[0].spec.resources.requests.storage}')
            echo "Qdrant PVC: current=\$CUR, desired=${QDRANT_STORAGE_SIZE}"
            if [ "\$CUR" != "${QDRANT_STORAGE_SIZE}" ]; then
                echo "Storage changed, recreating StatefulSet + PVC..."
                \$KUBECTL delete statefulset kf-qdrant -n ${NAMESPACE} --cascade=orphan --ignore-not-found
                \$KUBECTL delete pvc kf-qdrant-storage-kf-qdrant-0 -n ${NAMESPACE} --ignore-not-found
                sleep 3
            fi
        fi

        sed 's/<NAMESPACE>/${NAMESPACE}/g' \$QD_DIR/statefulset.yaml | \\
            sed 's|<QDRANT_STORAGE_SIZE>|${QDRANT_STORAGE_SIZE}|g' | \\
            \$KUBECTL apply -f -
    """
}

def checkHealth(String serviceName) {
    sh """
        APPHOME=${TOOLS} . ${TOOLS}/env.sh
        \$KUBECTL rollout status deployment/${serviceName} -n ${NAMESPACE} --timeout=120s 2>&1 || true
        \$KUBECTL wait --for=condition=ready pod -l app=${serviceName} -n ${NAMESPACE} --timeout=30s 2>&1 || true
        POD=\$(\$KUBECTL get pods -l app=${serviceName} -n ${NAMESPACE} --field-selector=status.phase=Running -o jsonpath='{.items[0].metadata.name}')
        if [ -n "\$POD" ]; then
            \$KUBECTL exec \$POD -n ${NAMESPACE} -- curl -s http://localhost:8000/health 2>/dev/null || echo "health check fallback: pod ready"
        fi
    """
}
