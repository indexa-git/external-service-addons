pipeline {
  agent any
  options { disableConcurrentBuilds() }
  environment {
    BRANCH = "${env.GIT_BRANCH}"
    ODOO_BRANCH = 12.0
    ODOO_IMAGE = "external_service_addons-${env.BRANCH}_odoo"
    PG_IMAGE = "external_service_addons-${env.BRANCH}_db"
    ADDONS_PATH = "${env.JENKINS_HOME}/odoo-addons"
    ODOO_DOCKER_PATH = "${env.JENKINS_HOME}/odoo-docker/docker"
    PORT = "8069"
  }
  stages {
    stage('Building Postgresql') {
      steps {
        sh "docker rm -f ${env.PG_IMAGE} || true"
        sh "docker run -d -e POSTGRES_USER=odoo -e POSTGRES_PASSWORD=odoo -e POSTGRES_DB=postgres --name ${env.PG_IMAGE} postgres:11"
      }
    }
    stage('Clonning Repository') {
      steps {
        sh "rm -rf ${env.ADDONS_PATH}"
        sh "mkdir -p ${env.ADDONS_PATH}"
        sh "cd ${env.ADDONS_PATH} && \
            git clone git@github.com:indexa-git/external_service_addons.git --branch ${env.BRANCH}"
      }
    }
    stage('Building Odoo') {
      steps {
        sh "docker rm -f ${env.ODOO_IMAGE} || true"
        sh "docker build ${env.ODOO_DOCKER_PATH}/${env.ODOO_BRANCH} -t odoo"
        sh "docker run \
            -p ${env.PORT}:8070 \
            --name ${env.ODOO_IMAGE} \
            -v ${env.ADDONS_PATH}:/etc/odoo-addons \
            --link ${env.PG_IMAGE}:db \
            -t \
            odoo \
            -d ${env.PG_IMAGE} \
            --addons-path=/etc/odoo/odoo/addons,/etc/odoo/addons,/etc/odoo-addons/external_service_addons \
            -i l10n_do_currency_update,l10n_do_rnc_validation \
            --stop-after-init \
            --test-enable"
        sh "docker stop ${env.ODOO_IMAGE}"
      }
    }
  }
}
