{{- define "pc-components.fullname" -}}
{{- .Release.Name | trunc 42 | trimSuffix "-" -}}
{{- end -}}
{{- define "pc-components.scopedname" -}}
{{- printf "%s-%s" .Release.Namespace .Release.Name | trunc 50 | trimSuffix "-" -}}
{{- end -}}
{{- define "pc-components.labels" -}}
app.kubernetes.io/name: pc-components
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end -}}
{{- define "pc-components.db-env" -}}
- name: DB_HOST
  value: {{ include "pc-components.fullname" . }}-postgres
- name: DB_PORT
  value: {{ .Values.db.port | quote }}
- name: DB_USER
  value: {{ .Values.db.user | quote }}
- name: DB_NAME
  value: {{ .Values.db.name | quote }}
- name: DB_PASSWORD
  valueFrom:
    secretKeyRef:
      name: {{ include "pc-components.fullname" . }}-db-auth
      key: password
{{- end -}}
