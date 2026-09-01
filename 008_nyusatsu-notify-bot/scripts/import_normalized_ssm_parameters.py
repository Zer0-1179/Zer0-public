#!/usr/bin/env python3
"""Create a value-safe CloudFormation IMPORT Change Set for normalized SSM.

The nine non-SecureString parameters are already in production.  CloudFormation
requires their current Value during import, so this tool retrieves each value and
sends it directly to the Change Set API in memory.  It never writes, prints, or
places a value on a command line.  It deliberately does not execute the Change
Set: that remains a separately reviewed operation.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

import boto3
from botocore.exceptions import ClientError


REGION = "ap-northeast-1"
STACK_NAME = "nyusatsu-ssm"
SECURE_PARAMETER = "/nyusatsu/stripe-webhook-secret-secure"
VALIDATOR_FUNCTION_NAME = "nyusatsu-ssm-secure-validator"
VALIDATOR_ROLE_NAME = "nyusatsu-ssm-secure-validator-role"
VALIDATOR_LOG_GROUP_NAME = "/aws/lambda/nyusatsu-ssm-secure-validator"
CFN_SYSTEM_TAG_KEYS = {
    "aws:cloudformation:stack-name",
    "aws:cloudformation:logical-id",
    "aws:cloudformation:stack-id",
}
PARAMETERS: tuple[tuple[str, str], ...] = (
    ("HmacSecretParameter", "/nyusatsu/hmac-secret"),
    ("KeywordsParameter", "/nyusatsu/keywords"),
    ("LineChannelAccessTokenParameter", "/nyusatsu/line-channel-access-token"),
    ("LineChannelSecretParameter", "/nyusatsu/line-channel-secret"),
    ("LineLiffIdParameter", "/nyusatsu/line-liff-id"),
    ("NotifyEmailParameter", "/nyusatsu/notify-email"),
    ("PaymentRequiredParameter", "/nyusatsu/payment-required"),
    ("SesSenderParameter", "/nyusatsu/ses-sender"),
    ("UnsubscribeBaseUrlParameter", "/nyusatsu/unsubscribe-base-url"),
)

VALIDATOR_SOURCE = '''import boto3
import json
import time
import urllib.request

def _physical_id(event):
    return event.get("PhysicalResourceId", f"{event['StackId']}/{event['LogicalResourceId']}")

def _respond(event, status, reason=None):
    body = {
        "Status": status,
        "PhysicalResourceId": _physical_id(event),
        "StackId": event["StackId"],
        "RequestId": event["RequestId"],
        "LogicalResourceId": event["LogicalResourceId"],
    }
    if status == "FAILED":
        body["Reason"] = reason or "ValidationFailed"
    encoded = json.dumps(body).encode("utf-8")
    request = urllib.request.Request(
        event["ResponseURL"], data=encoded, method="PUT",
        headers={"content-type": "", "content-length": str(len(encoded))},
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=10):
                return
        except Exception:
            if attempt == 2:
                raise
            time.sleep(1)

def lambda_handler(event, context):
    try:
        if event["RequestType"] == "Delete":
            _respond(event, "SUCCESS")
            return
        props = event["ResourceProperties"]
        name = props["ParameterName"]
        parameters = boto3.client("ssm").describe_parameters(
            ParameterFilters=[{"Key": "Name", "Option": "Equals", "Values": [name]}]
        )["Parameters"]
        if len(parameters) != 1:
            raise ValueError("ParameterMissing")
        parameter = parameters[0]
        if parameter.get("Type") != "SecureString":
            raise ValueError("ParameterTypeMismatch")
        if parameter.get("Tier") != "Standard" or parameter.get("DataType", "text") != "text":
            raise ValueError("ParameterMetadataMismatch")
        actual_tags = {
            item["Key"]: item["Value"]
            for item in boto3.client("ssm").list_tags_for_resource(
                ResourceType="Parameter", ResourceId=name
            )["TagList"]
        }
        if actual_tags != props["RequiredTags"]:
            raise ValueError("ParameterTagsMismatch")
        _respond(event, "SUCCESS")
    except Exception as error:
        try:
            _respond(event, "FAILED", type(error).__name__)
        except Exception:
            pass
'''


def metadata_by_name(ssm_client: Any) -> dict[str, dict[str, Any]]:
    """Load non-secret metadata for the normalized parameter namespace."""
    metadata: dict[str, dict[str, Any]] = {}
    paginator = ssm_client.get_paginator("describe_parameters")
    for page in paginator.paginate(
        ParameterFilters=[
            {
                "Key": "Name",
                "Option": "BeginsWith",
                "Values": ["/nyusatsu/"],
            }
        ]
    ):
        metadata.update({item["Name"]: item for item in page["Parameters"]})
    return metadata


def tags_by_name(ssm_client: Any, names: tuple[str, ...]) -> dict[str, dict[str, str]]:
    """Preserve the existing tags exactly without logging their contents."""
    tags: dict[str, dict[str, str]] = {}
    for name in names:
        response = ssm_client.list_tags_for_resource(
            ResourceType="Parameter",
            ResourceId=name,
        )
        tags[name] = {item["Key"]: item["Value"] for item in response["TagList"]}
    return tags


def user_tags_for_update(tags: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Remove only CFN-owned tags after verifying the imported resources own them."""
    normalized: dict[str, dict[str, str]] = {}
    for _, name in PARAMETERS:
        current_tags = tags[name]
        if not CFN_SYSTEM_TAG_KEYS.issubset(current_tags):
            raise ValueError("An imported String parameter is missing CloudFormation system tags")
        unknown_reserved_tags = {
            key for key in current_tags if key.startswith("aws:") and key not in CFN_SYSTEM_TAG_KEYS
        }
        if unknown_reserved_tags:
            raise ValueError("An imported String parameter has an unexpected reserved tag")
        normalized[name] = {
            key: value for key, value in current_tags.items() if not key.startswith("aws:")
        }
    secure_tags = tags[SECURE_PARAMETER]
    if any(key.startswith("aws:") for key in secure_tags):
        raise ValueError("The SecureString target has an unexpected reserved tag")
    normalized[SECURE_PARAMETER] = secure_tags
    return normalized


def validate_metadata(metadata: dict[str, dict[str, Any]]) -> None:
    """Reject absent, unexpected, or non-importable parameter metadata."""
    expected_names = {name for _, name in PARAMETERS} | {SECURE_PARAMETER}
    if set(metadata) != expected_names:
        raise ValueError("Normalized SSM namespace does not match the approved 10 parameters")
    for _, name in PARAMETERS:
        item = metadata[name]
        if item.get("Type") != "String" or item.get("Tier") != "Standard":
            raise ValueError("A String import target has an unexpected type or tier")
        if item.get("DataType", "text") != "text":
            raise ValueError("A String import target has an unexpected data type")
        if item.get("Policies"):
            raise ValueError("A String import target has a policy and requires a separate review")
    secure = metadata[SECURE_PARAMETER]
    if secure.get("Type") != "SecureString" or secure.get("Tier") != "Standard":
        raise ValueError("The SecureString target has an unexpected type or tier")


def parameter_resource(
    logical_id: str,
    name: str,
    metadata: dict[str, Any],
    tags: dict[str, str],
) -> dict[str, Any]:
    """Build one native SSM resource matching the currently existing parameter."""
    properties: dict[str, Any] = {
        "Name": name,
        "Type": "String",
        "Value": {"Ref": f"{logical_id}Value"},
        "Tier": "Standard",
        "DataType": "text",
        "Tags": tags,
    }
    if metadata.get("Description"):
        properties["Description"] = metadata["Description"]
    if metadata.get("AllowedPattern"):
        properties["AllowedPattern"] = metadata["AllowedPattern"]
    if metadata.get("Policies"):
        properties["Policies"] = metadata["Policies"]
    return {
        "Type": "AWS::SSM::Parameter",
        "DeletionPolicy": "Retain",
        "UpdateReplacePolicy": "Retain",
        "Properties": properties,
    }


def assert_unowned(cloudformation_client: Any, names: tuple[str, ...]) -> None:
    """Ensure an import target is not already managed by another stack."""
    for name in names:
        try:
            response = cloudformation_client.describe_stack_resources(
                PhysicalResourceId=name,
            )
        except ClientError as error:
            message = error.response.get("Error", {}).get("Message", "")
            if "does not exist" in message:
                continue
            raise
        if response.get("StackResources"):
            raise ValueError("An import target is already owned by CloudFormation")


def build_template(
    metadata: dict[str, dict[str, Any]],
    tags: dict[str, dict[str, str]],
    include_secure_validator: bool = False,
) -> dict[str, Any]:
    """Build the import template without embedding any parameter values."""
    resources = {
        logical_id: parameter_resource(logical_id, name, metadata[name], tags[name])
        for logical_id, name in PARAMETERS
    }
    parameters = {
        f"{logical_id}Value": {
            "Type": "String",
            "NoEcho": True,
            "Description": "Existing parameter value; supplied in memory only during import.",
        }
        for logical_id, _ in PARAMETERS
    }
    if include_secure_validator:
        resources.update(secure_validator_resources(tags[SECURE_PARAMETER]))
    return {
        "AWSTemplateFormatVersion": "2010-09-09",
        "Description": "Imports existing normalized Nyusatsu String parameters.",
        "Parameters": parameters,
        "Resources": resources,
    }


def secure_validator_resources(required_tags: dict[str, str]) -> dict[str, Any]:
    """Build the no-value SecureString adoption validator and its minimal provider."""
    parameter_arn = {
        "Fn::Sub": "arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:parameter/nyusatsu/stripe-webhook-secret-secure"
    }
    return {
        "SecureValidatorLogGroup": {
            "Type": "AWS::Logs::LogGroup",
            "DeletionPolicy": "Retain",
            "UpdateReplacePolicy": "Retain",
            "Properties": {"LogGroupName": VALIDATOR_LOG_GROUP_NAME, "RetentionInDays": 14},
        },
        "SecureValidatorRole": {
            "Type": "AWS::IAM::Role",
            "Properties": {
                "RoleName": VALIDATOR_ROLE_NAME,
                "Description": "Validates the Nyusatsu SecureString metadata without reading its value.",
                "AssumeRolePolicyDocument": {
                    "Version": "2012-10-17",
                    "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}],
                },
                "Policies": [{
                    "PolicyName": "validate-nyusatsu-secure-parameter-metadata",
                    "PolicyDocument": {
                        "Version": "2012-10-17",
                        "Statement": [
                            {"Effect": "Allow", "Action": ["ssm:DescribeParameters"], "Resource": "*"},
                            {"Effect": "Allow", "Action": ["ssm:ListTagsForResource"], "Resource": parameter_arn},
                            {"Effect": "Allow", "Action": ["logs:CreateLogStream", "logs:PutLogEvents"], "Resource": {"Fn::GetAtt": ["SecureValidatorLogGroup", "Arn"]}},
                        ],
                    },
                }],
            },
        },
        "SecureValidatorFunction": {
            "Type": "AWS::Lambda::Function",
            "Properties": {
                "FunctionName": VALIDATOR_FUNCTION_NAME,
                "Description": "Validates Nyusatsu SecureString metadata without reading the value.",
                "Runtime": "python3.14",
                "Handler": "index.lambda_handler",
                "Role": {"Fn::GetAtt": ["SecureValidatorRole", "Arn"]},
                "Timeout": 30,
                "MemorySize": 128,
                "Code": {"ZipFile": VALIDATOR_SOURCE},
            },
            "DependsOn": ["SecureValidatorLogGroup"],
        },
        "SecureParameterValidator": {
            "Type": "Custom::NyusatsuSecureParameterValidator",
            "DeletionPolicy": "Retain",
            "UpdateReplacePolicy": "Retain",
            "Properties": {
                "ServiceToken": {"Fn::GetAtt": ["SecureValidatorFunction", "Arn"]},
                "ServiceTimeout": 120,
                "ParameterName": SECURE_PARAMETER,
                "RequiredTags": required_tags,
            },
        },
    }


def current_values(ssm_client: Any) -> dict[str, str]:
    """Fetch String values solely for the in-memory Change Set request."""
    values: dict[str, str] = {}
    for logical_id, name in PARAMETERS:
        response = ssm_client.get_parameter(Name=name, WithDecryption=False)
        values[f"{logical_id}Value"] = response["Parameter"]["Value"]
    return values


def assert_stack_absent(cloudformation_client: Any) -> None:
    """IMPORT creates the dedicated ownership stack, never mutates an existing one."""
    try:
        cloudformation_client.describe_stacks(StackName=STACK_NAME)
    except ClientError as error:
        if "does not exist" in error.response.get("Error", {}).get("Message", ""):
            return
        raise
    raise ValueError("The dedicated SSM stack already exists; use a separately reviewed update")


def create_import_change_set(stack_name: str, change_set_name: str) -> None:
    """Create, but never execute, an IMPORT Change Set for the nine String parameters."""
    if stack_name != STACK_NAME:
        raise ValueError("The import stack name is fixed")
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("botocore").propagate = False
    session = boto3.session.Session(region_name=REGION)
    ssm_client = session.client("ssm")
    cloudformation_client = session.client("cloudformation")
    assert_stack_absent(cloudformation_client)

    metadata = metadata_by_name(ssm_client)
    validate_metadata(metadata)
    names = tuple(name for _, name in PARAMETERS)
    tags = tags_by_name(ssm_client, names)
    if any(any(key.startswith("aws:") for key in item_tags) for item_tags in tags.values()):
        raise ValueError("An import target has an AWS-reserved tag")
    assert_unowned(cloudformation_client, names)
    template = build_template(metadata, tags)
    values = current_values(ssm_client)
    resources_to_import = [
        {
            "ResourceType": "AWS::SSM::Parameter",
            "LogicalResourceId": logical_id,
            "ResourceIdentifier": {"Name": name},
        }
        for logical_id, name in PARAMETERS
    ]
    client_token = hashlib.sha256(
        json.dumps(
            {
                "stack": STACK_NAME,
                "change_set": change_set_name,
                "template": template,
                "resources": resources_to_import,
            },
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    cloudformation_client.create_change_set(
        StackName=stack_name,
        ChangeSetName=change_set_name,
        ChangeSetType="IMPORT",
        TemplateBody=json.dumps(template),
        Parameters=[
            {"ParameterKey": key, "ParameterValue": value}
            for key, value in values.items()
        ],
        ResourcesToImport=resources_to_import,
        ResourceTypes=["AWS::SSM::Parameter"],
        ClientToken=client_token,
    )
    cloudformation_client.get_waiter("change_set_create_complete").wait(
        StackName=stack_name,
        ChangeSetName=change_set_name,
    )
    changes: list[dict[str, Any]] = []
    next_token: str | None = None
    status: str | None = None
    execution_status: str | None = None
    change_set_type: str | None = None
    while True:
        request: dict[str, Any] = {
            "StackName": stack_name,
            "ChangeSetName": change_set_name,
            "IncludePropertyValues": False,
        }
        if next_token:
            request["NextToken"] = next_token
        response = cloudformation_client.describe_change_set(**request)
        status = response.get("Status")
        execution_status = response.get("ExecutionStatus")
        change_set_type = response.get("ChangeSetType")
        changes.extend(response.get("Changes", []))
        next_token = response.get("NextToken")
        if not next_token:
            break
    expected_logical_ids = {logical_id for logical_id, _ in PARAMETERS}
    actual_logical_ids = {
        item.get("ResourceChange", {}).get("LogicalResourceId") for item in changes
    }
    if (
        status != "CREATE_COMPLETE"
        or execution_status != "AVAILABLE"
        # DescribeChangeSet omits ChangeSetType for an IMPORT change set that
        # creates a new stack. The action/type/logical-ID checks below are the
        # authoritative scope guard in both response shapes.
        or (change_set_type is not None and change_set_type != "IMPORT")
        or len(changes) != len(PARAMETERS)
        or actual_logical_ids != expected_logical_ids
        or any(
            item.get("ResourceChange", {}).get("Action") != "Import"
            or item.get("ResourceChange", {}).get("ResourceType")
            != "AWS::SSM::Parameter"
            for item in changes
        )
    ):
        raise ValueError("The created Change Set is outside the approved import scope")
    print(f"IMPORT Change Set is ready for {len(PARAMETERS)} parameters; values redacted.")


def create_secure_validator_change_set(change_set_name: str) -> None:
    """Create, but never execute, the SecureString metadata validator Change Set."""
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("botocore").propagate = False
    session = boto3.session.Session(region_name=REGION)
    ssm_client = session.client("ssm")
    cloudformation_client = session.client("cloudformation")
    stack = cloudformation_client.describe_stacks(StackName=STACK_NAME)["Stacks"][0]
    if stack.get("StackStatus") not in {"IMPORT_COMPLETE", "UPDATE_COMPLETE"}:
        raise ValueError("The SSM ownership stack is not ready for an update")
    metadata = metadata_by_name(ssm_client)
    validate_metadata(metadata)
    all_names = tuple(name for _, name in PARAMETERS) + (SECURE_PARAMETER,)
    tags = tags_by_name(ssm_client, all_names)
    tags = user_tags_for_update(tags)
    template = build_template(metadata, tags, include_secure_validator=True)
    client_token = hashlib.sha256(
        json.dumps(
            {"stack": STACK_NAME, "change_set": change_set_name, "template": template},
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    cloudformation_client.create_change_set(
        StackName=STACK_NAME,
        ChangeSetName=change_set_name,
        ChangeSetType="UPDATE",
        TemplateBody=json.dumps(template),
        Parameters=[
            {"ParameterKey": f"{logical_id}Value", "UsePreviousValue": True}
            for logical_id, _ in PARAMETERS
        ],
        Capabilities=["CAPABILITY_NAMED_IAM"],
        ClientToken=client_token,
    )
    cloudformation_client.get_waiter("change_set_create_complete").wait(
        StackName=STACK_NAME,
        ChangeSetName=change_set_name,
    )
    response = cloudformation_client.describe_change_set(
        StackName=STACK_NAME,
        ChangeSetName=change_set_name,
        IncludePropertyValues=False,
    )
    expected_resources = {
        "SecureValidatorLogGroup": "AWS::Logs::LogGroup",
        "SecureValidatorRole": "AWS::IAM::Role",
        "SecureValidatorFunction": "AWS::Lambda::Function",
        "SecureParameterValidator": "Custom::NyusatsuSecureParameterValidator",
    }
    changes = response.get("Changes", [])
    actual_resources = {
        item.get("ResourceChange", {}).get("LogicalResourceId"):
        item.get("ResourceChange", {}).get("ResourceType")
        for item in changes
    }
    if (
        response.get("Status") != "CREATE_COMPLETE"
        or response.get("ExecutionStatus") != "AVAILABLE"
        or len(changes) != len(expected_resources)
        or actual_resources != expected_resources
        or any(item.get("ResourceChange", {}).get("Action") != "Add" for item in changes)
    ):
        raise ValueError("The validator Change Set is outside the approved scope")
    print("SecureString validator Change Set is ready; values redacted.")


def self_check() -> None:
    """Verify the static safety boundary without reading AWS or parameter values."""
    names = [name for _, name in PARAMETERS]
    if len(names) != 9 or len(set(names)) != 9 or SECURE_PARAMETER in names:
        raise ValueError("Unexpected import target set")
    if not all(name.startswith("/nyusatsu/") for name in names):
        raise ValueError("An import target is outside the normalized namespace")
    metadata = {
        name: {"Type": "String", "Tier": "Standard", "DataType": "text"}
        for name in names
    }
    metadata[SECURE_PARAMETER] = {
        "Type": "SecureString",
        "Tier": "Standard",
        "DataType": "text",
    }
    tags = {name: {"Project": "nyusatsu"} for name in names}
    tags[SECURE_PARAMETER] = {"Project": "nyusatsu"}
    template = build_template(metadata, tags)
    if len(template["Parameters"]) != 9 or len(template["Resources"]) != 9:
        raise ValueError("The import template target count is unexpected")
    if any(not item.get("NoEcho") for item in template["Parameters"].values()):
        raise ValueError("An import value is not NoEcho")
    if any(
        item.get("DeletionPolicy") != "Retain"
        or item.get("UpdateReplacePolicy") != "Retain"
        for item in template["Resources"].values()
    ):
        raise ValueError("An import target is not retained")
    if SECURE_PARAMETER in json.dumps(template):
        raise ValueError("SecureString was included in the import template")
    validator_template = build_template(metadata, tags, include_secure_validator=True)
    validator_resources = validator_template["Resources"]
    if set(validator_resources) != {
        logical_id for logical_id, _ in PARAMETERS
    } | {
        "SecureValidatorLogGroup",
        "SecureValidatorRole",
        "SecureValidatorFunction",
        "SecureParameterValidator",
    }:
        raise ValueError("The validator resource set is unexpected")
    provider_source = validator_resources["SecureValidatorFunction"]["Properties"]["Code"]["ZipFile"]
    if "get_parameter" in provider_source or "ssm:GetParameter" in json.dumps(validator_resources):
        raise ValueError("The validator can read a parameter value")
    print("Static safety checks passed; no AWS calls were made.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--self-check", action="store_true")
    mode.add_argument("--create-import-change-set", action="store_true")
    mode.add_argument("--create-secure-validator-change-set", action="store_true")
    parser.add_argument(
        "--change-set-name",
        default=f"import-normalized-string-params-{datetime.now(timezone.utc):%Y%m%d}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_check:
        self_check()
        return 0
    if args.create_secure_validator_change_set:
        create_secure_validator_change_set(args.change_set_name)
        return 0
    create_import_change_set(STACK_NAME, args.change_set_name)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Import Change Set was not created: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(1)
