#!/usr/bin/env bash
# Attach the AIOps tool permissions to the AgentCore Runtime execution role.
#
# Run this AFTER your first `agentcore deploy`. The CLI creates the execution
# role; this adds the CloudTrail + EC2 permissions the tools need.
#
#   ./attach-policy.sh <execution-role-name>
#
# Find the role name with:  agentcore status

set -euo pipefail

ROLE_NAME="${1:-}"
if [[ -z "$ROLE_NAME" ]]; then
  echo "usage: $0 <execution-role-name>   (get it from 'agentcore status')" >&2
  exit 1
fi

POLICY_FILE="$(dirname "$0")/agentcore-execution-policy.json"

aws iam put-role-policy \
  --role-name "$ROLE_NAME" \
  --policy-name AIOpsAgentToolPermissions \
  --policy-document "file://${POLICY_FILE}"

echo "Attached AIOpsAgentToolPermissions to ${ROLE_NAME}."
echo "Verify with: aws iam get-role-policy --role-name ${ROLE_NAME} --policy-name AIOpsAgentToolPermissions"
