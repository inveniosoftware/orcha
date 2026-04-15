{{/*
Expand the name of the chart.
*/}}
{{- define "orcha.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
We truncate at 63 chars because some Kubernetes name fields are limited to this (by the DNS naming spec).
If release name contains chart name, the release name will be used as a full name.
*/}}
{{- define "orcha.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Create chart name and version as used by the chart label.
*/}}
{{- define "orcha.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}


{{/*
Common labels
*/}}
{{- define "orcha.labels" -}}
helm.sh/chart: {{ include "orcha.chart" . }}
{{ include "orcha.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels
*/}}
{{- define "orcha.selectorLabels" -}}
app.kubernetes.io/name: {{ include "orcha.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Return the hostname for the Orcha service.
*/}}
{{- define "orcha.hostname" -}}
{{- .Values.host }}
{{- end }}

{{/*
Return the proper Orcha image name
*/}}
{{- define "orcha.image" -}}
{{- $registryName :=  required "Missing .Values.image.registry" .Values.image.registry -}}
{{- $repositoryName :=  required "Missing .Values.image.repository" .Values.image.repository -}}
{{- $separator := ":" -}}
{{- $termination := .Values.image.tag | default .Chart.AppVersion | toString -}}

{{- if .Values.image.digest }}
  {{- $separator = "@" -}}
  {{- $termination = .Values.image.digest | toString -}}
{{- end -}}

{{- printf "%s/%s%s%s" $registryName $repositoryName $separator $termination -}}
{{- end -}}

#########################     PostgreSQL connection configuration     #########################

{{/*
  This template renders the username used for the PostgreSQL instance.
*/}}
{{- define "orcha.postgresql.username" -}}
  {{- if .Values.postgresql.enabled -}}
    {{- required "Missing .Values.postgresql.auth.username" (tpl .Values.postgresql.auth.username .) -}}
  {{- else -}}
    {{- required "Missing .Values.postgresqlExternal.username" (tpl  .Values.postgresqlExternal.username .) -}}
  {{- end -}}
{{- end -}}

{{/*
  This template renders the password used for the PostgreSQL instance.
  In production environments we encourage you to use secrets instead.
*/}}
{{- define "orcha.postgresql.password" -}}
  {{- if .Values.postgresql.enabled -}}
    {{- required "Missing .Values.postgresql.auth.password" .Values.postgresql.auth.password -}}
  {{- else -}}
    {{- required "Missing .Values.postgresqlExternal.password" .Values.postgresqlExternal.password -}}
  {{- end -}}
{{- end -}}

{{/*
  Get the database password secret name
*/}}
{{- define "orcha.postgresql.secretName" -}}
  {{- if .Values.postgresql.enabled -}}
    {{- required "Missing .Values.postgresql.auth.existingSecret" (tpl .Values.postgresql.auth.existingSecret .) -}}
  {{- else -}}
    {{- required "Missing .Values.postgresqlExternal.existingSecret" (tpl .Values.postgresqlExternal.existingSecret .) -}}
  {{- end -}}
{{- end -}}

{{/*
  Get the database password secret key
*/}}
{{- define "orcha.postgresql.secretKey" -}}
  {{- if .Values.postgresql.enabled -}}
    {{- required "Missing .Values.postgresql.auth.secretKeys.userPasswordKey" .Values.postgresql.auth.secretKeys.userPasswordKey -}}
  {{- else -}}
    {{- required "Missing .Values.postgresqlExternal.existingSecretPasswordKey" .Values.postgresqlExternal.existingSecretPasswordKey -}}
  {{- end -}}
{{- end -}}

{{/*
  This template renders the hostname used for the PostgreSQL instance.
*/}}
{{- define "orcha.postgresql.hostname" -}}
  {{- if .Values.postgresql.enabled -}}
    {{- include "postgresql.v1.primary.fullname" .Subcharts.postgresql -}}
  {{- else -}}
    {{- required "Missing .Values.postgresqlExternal.hostname" (tpl .Values.postgresqlExternal.hostname .) -}}
  {{- end -}}
{{- end -}}

{{/*
  This template renders the port number used for the PostgreSQL instance (as a string).
*/}}
{{- define "orcha.postgresql.portString" -}}
  {{- if .Values.postgresql.enabled -}}
    {{- required "Missing .Values.postgresql.primary.service.ports.postgresql" (tpl (toString .Values.postgresql.primary.service.ports.postgresql) .) | quote -}}
  {{- else -}}
    {{- required "Missing .Values.postgresqlExternal.port" (tpl (toString .Values.postgresqlExternal.port) .) | quote -}}
  {{- end -}}
{{- end -}}

{{/*
  This template renders the name of the database in PostgreSQL.
*/}}
{{- define "orcha.postgresql.database" -}}
  {{- if .Values.postgresql.enabled -}}
    {{- required "Missing .Values.postgresql.auth.database" (tpl .Values.postgresql.auth.database .) -}}
  {{- else -}}
    {{- required "Missing .Values.postgresqlExternal.database" (tpl .Values.postgresqlExternal.database .) -}}
  {{- end -}}
{{- end -}}

{{/*
  Define database connection env section.
*/}}
{{- define "orcha.config.database" -}}
- name: ORCHA_DB_USER
  value: {{ include "orcha.postgresql.username" . }}
- name: ORCHA_DB_HOST
  value: {{ include "orcha.postgresql.hostname" . }}
- name: ORCHA_DB_PORT
  value: {{ include "orcha.postgresql.portString" . }}
- name: ORCHA_DB_NAME
  value: {{ include "orcha.postgresql.database" . }}
- name: ORCHA_DB_PROTOCOL
  value: "postgresql+psycopg2"
- name: ORCHA_DB_PASSWORD
{{- if or (and .Values.postgresql.enabled .Values.postgresql.auth.password) .Values.postgresqlExternal.password }}
  value: {{ include "orcha.postgresql.password" .  | quote }}
{{- else }}
  valueFrom:
    secretKeyRef:
      name: {{ include "orcha.postgresql.secretName" .}}
      key: {{ include "orcha.postgresql.secretKey" .}}
{{- end }}
- name: ORCHA_EXTERNAL_DATABASE_URI
  value: "$(ORCHA_DB_PROTOCOL)://$(ORCHA_DB_USER):$(ORCHA_DB_PASSWORD)@$(ORCHA_DB_HOST):$(ORCHA_DB_PORT)/$(ORCHA_DB_NAME)"
{{- end -}}

{{/*
Orcha basic configuration variables
*/}}
{{- define "orcha.configBase" -}}
ORCHA_TRUSTED_HOSTS: '["{{ include "orcha.hostname" $ }}"]'
ORCHA_SITE_HOSTNAME: '{{ include "orcha.hostname" $ }}'
ORCHA_SITE_UI_URL: 'https://{{ include "orcha.hostname" $ }}'
ORCHA_SITE_API_URL: 'https://{{ include "orcha.hostname" $ }}/api'
{{- end -}}

{{/*
Get the Orcha general secret name
*/}}
{{- define "orcha.secretName" -}}
{{- if .Values.orcha.existingSecret -}}
  {{- tpl .Values.orcha.existingSecret . -}}
{{- else -}}
  {{- include "orcha.fullname" . -}}
{{- end -}}
{{- end -}}