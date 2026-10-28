pipeline {
    agent {
        node {
            label 'edgeops-windows'
            customWorkspace "${env.EDGEOPS_PROJECT_DIR}"
        }
    }
    options {
        disableConcurrentBuilds()
        skipDefaultCheckout(true)
        timeout(time: 30, unit: 'MINUTES')
        buildDiscarder(logRotator(numToKeepStr: '10'))
    }
    parameters {
        booleanParam(name: 'DEPLOY_AWS', defaultValue: false,
            description: 'Apply this build\'s reviewed code-only plan to the existing EdgeOps AWS stack.')
    }
    stages {
        stage('Application and guard tests') {
            steps { bat '@"%EDGEOPS_PYTHON%" scripts\\pipeline.py tests' }
        }
        stage('Docker build and loopback health') {
            steps { bat '@"%EDGEOPS_PYTHON%" scripts\\pipeline.py docker' }
        }
        stage('AWS target and Terraform validation') {
            steps { bat '@"%EDGEOPS_PYTHON%" scripts\\pipeline.py validate' }
        }
        stage('Plan and review code-only changes') {
            steps { bat '@"%EDGEOPS_PYTHON%" scripts\\pipeline.py plan' }
        }
        stage('Apply reviewed saved plan') {
            when { expression { params.DEPLOY_AWS == true } }
            steps { bat '@"%EDGEOPS_PYTHON%" scripts\\pipeline.py apply --approved' }
        }
        stage('Read-only cloud smoke checks') {
            steps { bat '@"%EDGEOPS_PYTHON%" scripts\\pipeline.py smoke' }
        }
    }
    post {
        always {
            archiveArtifacts artifacts: "reports/pipeline/${env.BUILD_TAG}/tests.json,reports/pipeline/${env.BUILD_TAG}/docker.json,reports/pipeline/${env.BUILD_TAG}/terraform-validation.json,reports/pipeline/${env.BUILD_TAG}/plan-review.json,reports/pipeline/${env.BUILD_TAG}/apply.json,reports/pipeline/${env.BUILD_TAG}/cloud-smoke.json,reports/pipeline/${env.BUILD_TAG}/authenticated-health.json",
                allowEmptyArchive: true
        }
        success { echo 'Checks passed. AWS apply runs only when DEPLOY_AWS is selected; no-op applies create no resource changes.' }
    }
}
