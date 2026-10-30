#!/usr/bin/env bash
set -euo pipefail

API_BASE="${API_BASE:-http://localhost:8000/api}"
API_HOST="${API_HOST:-localhost}"

for command_name in curl jq; do
    if ! command -v "$command_name" >/dev/null 2>&1; then
        printf 'Falta el comando requerido: %s\n' "$command_name" >&2
        exit 1
    fi
done

login() {
    local email="$1"
    local password="$2"
    local response

    response="$(
        curl --silent --show-error --fail-with-body \
            --header "Host: ${API_HOST}" \
            --header "Content-Type: application/json" \
            --request POST \
            --data "$(jq -cn --arg email "$email" --arg password "$password" \
                '{email: $email, password: $password}')" \
            "${API_BASE}/auth/login/"
    )"
    printf '%s' "$response" | jq -er '.tokens.access'
}

get_json() {
    curl --silent --show-error --fail-with-body \
        --header "Host: ${API_HOST}" \
        --header "Authorization: Bearer $1" \
        "${API_BASE}/$2"
}

expect_get() {
    local token="$1"
    local path="$2"
    local response
    local status

    response="$(
        curl --silent --show-error \
            --output /dev/null \
            --write-out '%{http_code}' \
            --header "Host: ${API_HOST}" \
            --header "Authorization: Bearer ${token}" \
            "${API_BASE}/${path}"
    )"
    status="$response"
    printf 'GET /%s -> HTTP %s\n' "$path" "$status"
    if [[ "$status" != "200" ]]; then
        printf 'Se esperaba HTTP 200 para esta lectura.\n' >&2
        return 1
    fi
}

printf 'API: %s\n' "$API_BASE"
read -r -p 'Correo del productor: ' producer_email
read -r -s -p 'Contraseña del productor: ' producer_password
printf '\n'
printf 'Paso 1/7: iniciando sesión del productor...\n'
producer_token="$(login "$producer_email" "$producer_password")"
unset producer_password

read -r -p 'Correo del operario: ' operator_email
read -r -s -p 'Contraseña del operario: ' operator_password
printf '\n'
printf 'Paso 2/7: iniciando sesión del operario...\n'
operator_token="$(login "$operator_email" "$operator_password")"
unset operator_password

producer_profile="$(get_json "$producer_token" 'users/me/')"
operator_profile="$(get_json "$operator_token" 'users/me/')"
producer_id="$(printf '%s' "$producer_profile" | jq -er '.id')"
operator_id="$(printf '%s' "$operator_profile" | jq -er '.id')"

producer_farms="$(get_json "$producer_token" 'farms/')"
operator_farms="$(get_json "$operator_token" 'farms/')"
printf 'Paso 3/7: fincas visibles para el productor:\n'
printf '%s' "$producer_farms" | jq -r '.[] | "  \(.id): \(.name)"'
printf 'Fincas visibles para el operario:\n'
printf '%s' "$operator_farms" | jq -r '.[] | "  \(.id): \(.name)"'

read -r -p 'ID de la finca que se va a probar: ' farm_id
if [[ ! "$farm_id" =~ ^[0-9]+$ ]]; then
    printf 'El ID debe ser numérico.\n' >&2
    exit 1
fi

members="$(get_json "$producer_token" "farms/${farm_id}/members/")"
producer_is_owner="$(
    printf '%s' "$members" |
        jq -er --argjson id "$producer_id" \
            'any(.[]; .user_id == $id and .is_owner == true)'
)"
operator_is_member="$(
    printf '%s' "$members" |
        jq -er --argjson id "$operator_id" \
            'any(.[]; .user_id == $id and .status == "active")'
)"
if [[ "$producer_is_owner" != "true" || "$operator_is_member" != "true" ]]; then
    printf 'El productor debe ser propietario y el operario miembro activo de la finca seleccionada.\n' >&2
    exit 1
fi

printf 'Paso 4/7: membresías registradas para la finca %s:\n' "$farm_id"
printf '%s' "$members" |
    jq -r '.[] | "  usuario=\(.user_id) propietario=\(.is_owner) estado=\(.status) rol=\(.farm_role // "-") permisos=\(.permissions | join(","))"'

printf 'Paso 5/7: permisos y aplicaciones del rol de finca:\n'
roles="$(get_json "$producer_token" "farms/${farm_id}/roles/")"
printf '%s' "$roles" |
    jq -r '.[] | "  rol=\(.id) nombre=\(.name) permisos=\(.permissions | join(",")) apps=\([.app_permissions[]? | "\(.app):view=\(.can_view),create=\(.can_create),edit=\(.can_edit),delete=\(.can_delete)"] | join(";"))"'

printf 'Paso 6/7: lecturas del productor:\n'
expect_get "$producer_token" "farms/${farm_id}/ponds/"
expect_get "$producer_token" "farms/${farm_id}/batches/"
expect_get "$producer_token" "farms/${farm_id}/production-plans/"
expect_get "$producer_token" "farms/${farm_id}/daily-stats/"
expect_get "$producer_token" "farms/${farm_id}/control-stats/"
expect_get "$producer_token" "farms/${farm_id}/products/"

printf 'Paso 7/7: lecturas del operario con los permisos actuales:\n'
expect_get "$operator_token" "farms/${farm_id}/roles/"
expect_get "$operator_token" "farms/${farm_id}/members/"
expect_get "$operator_token" "farms/${farm_id}/ponds/"
expect_get "$operator_token" "farms/${farm_id}/batches/"
expect_get "$operator_token" "farms/${farm_id}/production-plans/"
expect_get "$operator_token" "farms/${farm_id}/daily-stats/"
expect_get "$operator_token" "farms/${farm_id}/control-stats/"
expect_get "$operator_token" "farms/${farm_id}/products/"

printf 'Prueba completada. No se crearon ni modificaron registros.\n'
