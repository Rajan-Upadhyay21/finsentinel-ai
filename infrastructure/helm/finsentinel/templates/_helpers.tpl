{{/* FinSentinel chart name */}}
{{- define "finsentinel.name" -}}
finsentinel
{{- end }}

{{/* FinSentinel release fullname */}}
{{- define "finsentinel.fullname" -}}
{{- .Release.Name -}}
{{- end }}

{{/* FinSentinel service account */}}
{{- define "finsentinel.serviceAccount" -}}
{{ include "finsentinel.fullname" . }}-sa
{{- end }}

{{/* Backwards-compatible service-account helper */}}
{{- define "finsentinel.serviceAccountName" -}}
{{ include "finsentinel.serviceAccount" . }}
{{- end }}
