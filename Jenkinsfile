// CI produces a reviewable GitOps change. Argo CD, not Jenkins, applies Kubernetes resources.
pipeline {
    agent { label 'build' }
    tools { jdk 'java21'; maven 'maven3' }
    options {
        skipDefaultCheckout(true)
        timeout(time: 35, unit: 'MINUTES')
        disableConcurrentBuilds()
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    parameters {
        booleanParam(name: 'PUBLISH_IMAGE', defaultValue: false, description: 'Publish from trusted main using the agent IAM role')
        string(name: 'AWS_ACCOUNT_ID', defaultValue: '', description: 'Your 12 digit AWS account ID')
        string(name: 'AWS_REGION', defaultValue: 'ap-south-1', description: 'ECR region')
        string(name: 'ECR_REPOSITORY', defaultValue: 'merchant-payments', description: 'Existing immutable ECR repository')
    }
    stages {
        stage('Checkout') {
            steps {
                deleteDir()
                checkout scm
                script {
                    env.SOURCE_COMMIT = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
                    env.RUN_ID = 'mp-' + sh(script: 'printf "%s" "$JOB_NAME:$BUILD_NUMBER" | sha256sum | cut -c1-24', returnStdout: true).trim()
                    env.APP_IMAGE = "merchant-payments-ci:${env.RUN_ID}"
                    env.SMOKE_CONTAINER = env.RUN_ID
                }
            }
        }
        stage('Build and payment behavior tests') {
            steps { sh 'mvn --batch-mode --no-transfer-progress clean verify' }
        }
        stage('GitOps promotion policy tests') {
            steps { sh 'python3 -m unittest discover -s tests_gitops -v' }
        }
        stage('Helm, secret and infrastructure checks') {
            steps { sh 'bash .ci/image.sh config' }
        }
        stage('Build image once') {
            steps { sh 'bash .ci/image.sh build' }
        }
        stage('Dependency/image gate and SBOM') {
            steps { sh 'bash .ci/image.sh scan' }
        }
        stage('Container smoke check') {
            steps { sh 'bash .ci/image.sh smoke' }
        }
        stage('Publish tested image to ECR') {
            when { allOf { branch 'main'; expression { params.PUBLISH_IMAGE } } }
            steps { sh 'bash .ci/image.sh publish' }
        }
        stage('Prepare staging GitOps proposal') {
            when { allOf { branch 'main'; expression { params.PUBLISH_IMAGE } } }
            steps {
                sh 'python3 scripts/gitops.py stage --release reports/release.json'
                sh 'git diff -- deploy/chart/environments/staging.json > reports/staging-promotion.patch'
                echo 'Review the patch and merge an authorized Git change. Argo CD detects the merged values.'
            }
        }
    }
    post {
        always { junit allowEmptyResults: true, testResults: 'target/surefire-reports/TEST-*.xml' }
        success { archiveArtifacts artifacts: 'target/merchant-payments.jar', fingerprint: true }
        cleanup {
            sh 'if [ -f .ci/image.sh ]; then bash .ci/image.sh cleanup; fi'
            archiveArtifacts artifacts: 'reports/*.json,reports/*.patch', allowEmptyArchive: true, fingerprint: true
        }
    }
}
