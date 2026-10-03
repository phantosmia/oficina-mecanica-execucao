#!/bin/bash
set -e

# Mesma imagem para os três processos do serviço:
#   docker-entrypoint.sh            -> API (uvicorn), usada pelo mecânico
#   docker-entrypoint.sh worker     -> consumidor da fila de comandos da saga
#   docker-entrypoint.sh relay      -> relay da outbox (publica eventos no SNS)
ROLE="${1:-api}"

# Só no docker-compose (LocalStack): na AWS, tabela, fila e tópico vêm do Terraform.
if [ "${BOOTSTRAP_LOCAL_RESOURCES:-false}" = "true" ]; then
    echo "Criando tabela, fila e tópico locais..."
    python -m scripts.bootstrap_local
fi

# Agente APM do New Relic (ADR-0007) só quando a license key estiver definida.
RUNNER=()
if [ -n "${NEW_RELIC_LICENSE_KEY:-}" ]; then
    RUNNER=(newrelic-admin run-program)
fi

case "$ROLE" in
    worker)
        echo "Iniciando worker da fila de comandos..."
        exec "${RUNNER[@]}" python -m app.worker
        ;;
    relay)
        echo "Iniciando relay da outbox..."
        exec "${RUNNER[@]}" python -m app.outbox_relay
        ;;
    *)
        echo "Iniciando API da Execução..."
        exec "${RUNNER[@]}" uvicorn app.main:app --host 0.0.0.0 --port 8000
        ;;
esac
