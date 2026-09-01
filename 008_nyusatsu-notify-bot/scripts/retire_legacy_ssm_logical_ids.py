#!/usr/bin/env python3
"""Create guarded Change Sets to detach deleted legacy SSM logical resources.

This tool operates only on the two Nyusatsu application stacks and never prints
template bodies or parameter values.  The retain phase first adds Retain
policies.  The detach phase then removes exactly the same logical resources.
Both modes create Change Sets only; execution is deliberately separate.
"""

from __future__ import annotations

import argparse
import hashlib
import logging
import re
import sys
from datetime import datetime, timezone
from typing import Any

import boto3


REGION = "ap-northeast-1"
STACK_TARGETS: dict[str, tuple[str, ...]] = {
    "zer0-nyusatsu-notify-bot": (
        "HmacSecretParameter",
        "KeywordsParameter",
        "NotifyEmailParameter",
        "PaymentRequiredParameter",
        "SesSenderParameter",
    ),
    "zer0-nyusatsu-lp-backend": (
        "LineChannelAccessTokenParameter",
        "LineChannelSecretParameter",
        "LineLiffIdParameter",
        "StripeWebhookSecretParameter",
        "UnsubscribeBaseUrlParameter",
    ),
}
NORMALIZED_PATHS = {
    "HmacSecretParameter": "/nyusatsu/hmac-secret",
    "KeywordsParameter": "/nyusatsu/keywords",
    "NotifyEmailParameter": "/nyusatsu/notify-email",
    "PaymentRequiredParameter": "/nyusatsu/payment-required",
    "SesSenderParameter": "/nyusatsu/ses-sender",
    "LineChannelAccessTokenParameter": "/nyusatsu/line-channel-access-token",
    "LineChannelSecretParameter": "/nyusatsu/line-channel-secret",
    "LineLiffIdParameter": "/nyusatsu/line-liff-id",
    "StripeWebhookSecretParameter": "/nyusatsu/stripe-webhook-secret-secure",
    "UnsubscribeBaseUrlParameter": "/nyusatsu/unsubscribe-base-url",
}
DECOUPLE_TARGETS = {
    "zer0-nyusatsu-notify-bot": {
        "function": "CollectorFunction",
        "role": "CollectorFunctionRole",
        "environment": {
            "HMAC_SECRET_PARAM_NAME": "HmacSecretParameter",
            "KEYWORDS_PARAM_NAME": "KeywordsParameter",
            "NOTIFY_EMAIL_PARAM_NAME": "NotifyEmailParameter",
            "PAYMENT_REQUIRED_PARAM_NAME": "PaymentRequiredParameter",
            "SES_SENDER_PARAM_NAME": "SesSenderParameter",
        },
        "role_parameters": STACK_TARGETS["zer0-nyusatsu-notify-bot"],
    },
    "zer0-nyusatsu-lp-backend": {
        "function": "WaitlistFunction",
        "role": "WaitlistFunctionRole",
        "environment": {
            "LINE_CHANNEL_ACCESS_TOKEN_PARAM_NAME": "LineChannelAccessTokenParameter",
            "LINE_CHANNEL_SECRET_PARAM_NAME": "LineChannelSecretParameter",
            "LINE_LIFF_ID_PARAM_NAME": "LineLiffIdParameter",
        },
        "role_parameters": (
            "LineChannelAccessTokenParameter",
            "LineChannelSecretParameter",
            "LineLiffIdParameter",
        ),
        "secondary_function": "StripeWebhookFunction",
        "secondary_role": "StripeWebhookFunctionRole",
        "secondary_environment": {"STRIPE_WEBHOOK_SECRET_PARAM_NAME": "StripeWebhookSecretParameter"},
        "secondary_role_parameters": ("StripeWebhookSecretParameter",),
    },
}


def top_level_resource_block(template: str, logical_id: str) -> tuple[int, int, str]:
    """Return one two-space-indented resource block without parsing its values."""
    start_match = re.search(rf"(?m)^  {re.escape(logical_id)}:\n", template)
    if not start_match:
        raise ValueError("An approved legacy SSM logical resource is absent")
    next_match = re.search(
        r"(?m)^(?:  [A-Za-z][A-Za-z0-9]*:|Outputs:|Conditions:|Mappings:|Metadata:|Rules:)",
        template[start_match.end():],
    )
    end = start_match.end() + next_match.start() if next_match else len(template)
    block = template[start_match.start():end]
    return start_match.start(), end, block


def resource_block(template: str, logical_id: str) -> tuple[int, int, str]:
    """Return an approved legacy SSM resource block only."""
    start, end, block = top_level_resource_block(template, logical_id)
    if "Type: AWS::SSM::Parameter" not in block:
        raise ValueError("An approved logical ID is not an SSM parameter")
    return start, end, block


def with_retain_policies(template: str, logical_ids: tuple[str, ...]) -> str:
    """Add Retain policies to only the approved legacy SSM resource blocks."""
    staged = template
    for logical_id in logical_ids:
        start, end, block = resource_block(staged, logical_id)
        has_deletion_policy = "DeletionPolicy:" in block
        has_update_policy = "UpdateReplacePolicy:" in block
        if has_deletion_policy != has_update_policy:
            raise ValueError("A legacy SSM resource has an incomplete lifecycle policy")
        if has_deletion_policy:
            if "DeletionPolicy: Retain" not in block or "UpdateReplacePolicy: Retain" not in block:
                raise ValueError("A legacy SSM resource has an unexpected lifecycle policy")
            continue
        replacement = block.replace(
            "    Type: AWS::SSM::Parameter\n",
            "    DeletionPolicy: Retain\n    UpdateReplacePolicy: Retain\n    Type: AWS::SSM::Parameter\n",
            1,
        )
        staged = staged[:start] + replacement + staged[end:]
    return staged


def retain_change_ids(template: str, logical_ids: tuple[str, ...]) -> set[str]:
    """Return only the target resources that still require Retain policies."""
    change_ids: set[str] = set()
    for logical_id in logical_ids:
        _, _, block = resource_block(template, logical_id)
        has_deletion_policy = "DeletionPolicy:" in block
        has_update_policy = "UpdateReplacePolicy:" in block
        if has_deletion_policy != has_update_policy:
            raise ValueError("A legacy SSM resource has an incomplete lifecycle policy")
        if not has_deletion_policy:
            change_ids.add(logical_id)
        elif "DeletionPolicy: Retain" not in block or "UpdateReplacePolicy: Retain" not in block:
            raise ValueError("A legacy SSM resource has an unexpected lifecycle policy")
    return change_ids


def without_legacy_resources(template: str, logical_ids: tuple[str, ...]) -> str:
    """Remove only the approved legacy SSM resource blocks after Retain is present."""
    staged = template
    for logical_id in logical_ids:
        start, end, block = resource_block(staged, logical_id)
        if "DeletionPolicy: Retain" not in block or "UpdateReplacePolicy: Retain" not in block:
            raise ValueError("A legacy SSM resource is not protected by Retain")
        staged = staged[:start] + staged[end:]
    return staged


def replace_once_in_resource(
    template: str,
    owner_logical_id: str,
    expected: str,
    replacement: str,
) -> str:
    """Replace one complete, approved line inside one named resource block."""
    start, end, block = top_level_resource_block(template, owner_logical_id)
    if block.count(expected) != 1:
        raise ValueError("An approved legacy reference is absent or ambiguous")
    updated_block = block.replace(expected, replacement, 1)
    return template[:start] + updated_block + template[end:]


def decouple_references(template: str, stack_name: str) -> str:
    """Replace only approved Lambda env and IAM SSM ARN references with normalized paths."""
    target = DECOUPLE_TARGETS[stack_name]
    staged = template

    def replace_environment(function_id: str, references: dict[str, str]) -> None:
        nonlocal staged
        for key, logical_id in references.items():
            expected = f"          {key}: !Ref {logical_id}"
            replacement = f"          {key}: {NORMALIZED_PATHS[logical_id]}"
            staged = replace_once_in_resource(staged, function_id, expected, replacement)

    def replace_role(role_id: str, logical_ids: tuple[str, ...]) -> None:
        nonlocal staged
        for logical_id in logical_ids:
            expected = (
                "              - !Sub arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:"
                f"parameter${{{logical_id}}}"
            )
            replacement = (
                "              - !Sub arn:aws:ssm:${AWS::Region}:${AWS::AccountId}:"
                f"parameter{NORMALIZED_PATHS[logical_id]}"
            )
            staged = replace_once_in_resource(staged, role_id, expected, replacement)

    replace_environment(target["function"], target["environment"])
    replace_role(target["role"], target["role_parameters"])
    if "secondary_function" in target:
        replace_environment(target["secondary_function"], target["secondary_environment"])
        replace_role(target["secondary_role"], target["secondary_role_parameters"])
    return staged


def resource_ids(template: str) -> set[str]:
    """Return logical IDs in Resources without examining property values."""
    resources_match = re.search(r"(?m)^Resources:\n", template)
    if not resources_match:
        raise ValueError("The template has no Resources section")
    next_section = re.search(r"(?m)^[A-Za-z][A-Za-z0-9]*:\n", template[resources_match.end():])
    resources_end = resources_match.end() + next_section.start() if next_section else len(template)
    return set(re.findall(r"(?m)^  ([A-Za-z][A-Za-z0-9]*):\n", template[resources_match.end():resources_end]))


def assert_decouple_integrity(original: str, staged: str, stack_name: str) -> None:
    """Prove that only the approved function and role blocks were edited."""
    target = DECOUPLE_TARGETS[stack_name]
    owners = {target["function"], target["role"]}
    if "secondary_function" in target:
        owners.update({target["secondary_function"], target["secondary_role"]})
    if resource_ids(original) != resource_ids(staged):
        raise ValueError("The decouple transformation changed resource membership")
    for logical_id in resource_ids(original):
        _, _, before = top_level_resource_block(original, logical_id)
        _, _, after = top_level_resource_block(staged, logical_id)
        if logical_id not in owners and before != after:
            raise ValueError("The decouple transformation changed an unapproved resource")
    for logical_id in STACK_TARGETS[stack_name]:
        _, _, before = resource_block(original, logical_id)
        _, _, after = resource_block(staged, logical_id)
        if before != after:
            raise ValueError("The decouple transformation changed a legacy SSM resource")


def current_parameters(cloudformation_client: Any, stack_name: str) -> list[dict[str, Any]]:
    """Reuse every current stack input without retrieving or resending its value."""
    stack = cloudformation_client.describe_stacks(StackName=stack_name)["Stacks"][0]
    return [
        {"ParameterKey": parameter["ParameterKey"], "UsePreviousValue": True}
        for parameter in stack.get("Parameters", [])
    ]


def inspect_references(stack_name: str) -> None:
    """Report legacy logical-ID references without printing template values."""
    if stack_name not in STACK_TARGETS:
        raise ValueError("The target stack is not approved")
    cloudformation_client = boto3.session.Session(region_name=REGION).client("cloudformation")
    template = cloudformation_client.get_template(
        StackName=stack_name,
        TemplateStage="Original",
    )["TemplateBody"]
    if not isinstance(template, str):
        raise ValueError("The live template is not text")
    for logical_id in STACK_TARGETS[stack_name]:
        patterns = (
            rf"!Ref\s+{re.escape(logical_id)}\b",
            rf"!GetAtt\s+{re.escape(logical_id)}\b",
            rf"\$\{{{re.escape(logical_id)}(?:[.}}])",
        )
        counts = [len(re.findall(pattern, template)) for pattern in patterns]
        print(f"{logical_id}: Ref={counts[0]} GetAtt={counts[1]} Sub={counts[2]}")


def is_direct_property_modification(item: dict[str, Any]) -> bool:
    """Return whether a Change Set modifies properties without replacement."""
    change = item.get("ResourceChange", {})
    details = change.get("Details", [])
    return (
        change.get("Action") == "Modify"
        and str(change.get("Replacement")).lower() == "false"
        and change.get("Scope") == ["Properties"]
        and bool(details)
        and all(
            detail.get("ChangeSource") == "DirectModification"
            and detail.get("Target", {}).get("Attribute") == "Properties"
            and detail.get("Target", {}).get("RequiresRecreation") == "Never"
            for detail in details
        )
    )


def is_retain_policy_modification(item: dict[str, Any]) -> bool:
    """Return whether only non-replacing Retain policies are added."""
    change = item.get("ResourceChange", {})
    details = change.get("Details", [])
    expected_attributes = {"DeletionPolicy", "UpdateReplacePolicy"}
    return (
        change.get("Action") == "Modify"
        and str(change.get("Replacement")).lower() == "false"
        and change.get("PolicyAction") in (None, "Retain")
        and set(change.get("Scope", [])) == expected_attributes
        and len(details) == len(expected_attributes)
        and {detail.get("Target", {}).get("Attribute") for detail in details}
        == expected_attributes
        and all(
            detail.get("ChangeSource") == "DirectModification"
            and detail.get("Target", {}).get("RequiresRecreation") == "Never"
            for detail in details
        )
    )


def is_retained_removal(item: dict[str, Any]) -> bool:
    """Return whether CloudFormation will remove only the stack record."""
    change = item.get("ResourceChange", {})
    return (
        change.get("Action") == "Remove"
        and change.get("PolicyAction") == "Retain"
        and change.get("Replacement") is None
        and not change.get("Scope")
        and not change.get("Details")
    )


def print_change_summary(changes: list[dict[str, Any]]) -> None:
    """Print only safe Change Set metadata for a failed-scope diagnosis."""
    for item in changes:
        change = item.get("ResourceChange", {})
        details = [
            {
                "ChangeSource": detail.get("ChangeSource"),
                "Attribute": detail.get("Target", {}).get("Attribute"),
                "Name": detail.get("Target", {}).get("Name"),
                "RequiresRecreation": detail.get("Target", {}).get("RequiresRecreation"),
            }
            for detail in change.get("Details", [])
        ]
        print(
            {
                "Action": change.get("Action"),
                "PolicyAction": change.get("PolicyAction"),
                "LogicalId": change.get("LogicalResourceId"),
                "Type": change.get("ResourceType"),
                "Replacement": change.get("Replacement"),
                "Scope": change.get("Scope", []),
                "Details": details,
            }
        )


def create_change_set(stack_name: str, phase: str, change_set_name: str) -> None:
    """Create and inspect one retain or detach Change Set; never execute it."""
    if stack_name not in STACK_TARGETS:
        raise ValueError("The target stack is not approved")
    logging.getLogger("botocore").setLevel(logging.WARNING)
    logging.getLogger("botocore").propagate = False
    cloudformation_client = boto3.session.Session(region_name=REGION).client("cloudformation")
    original = cloudformation_client.get_template(
        StackName=stack_name,
        TemplateStage="Original",
    )["TemplateBody"]
    if not isinstance(original, str) or not original.startswith("AWSTemplateFormatVersion"):
        raise ValueError("The live template is not the expected YAML format")
    logical_ids = STACK_TARGETS[stack_name]
    expected_ids = (
        retain_change_ids(original, logical_ids)
        if phase == "retain"
        else (
            set(logical_ids)
            if phase == "detach"
            else {
                DECOUPLE_TARGETS[stack_name]["function"],
                DECOUPLE_TARGETS[stack_name]["role"],
                *(
                    {
                        DECOUPLE_TARGETS[stack_name]["secondary_function"],
                        DECOUPLE_TARGETS[stack_name]["secondary_role"],
                    }
                    if "secondary_function" in DECOUPLE_TARGETS[stack_name]
                    else set()
                ),
            }
        )
    )
    if not expected_ids:
        raise ValueError("All approved legacy SSM resources already have Retain policies")
    template = (
        with_retain_policies(original, logical_ids)
        if phase == "retain"
        else without_legacy_resources(original, logical_ids)
        if phase == "detach"
        else decouple_references(original, stack_name)
    )
    if phase == "decouple":
        assert_decouple_integrity(original, template, stack_name)
    token = hashlib.sha256(
        f"{stack_name}:{phase}:{change_set_name}:{template}".encode("utf-8")
    ).hexdigest()
    created = False
    try:
        cloudformation_client.create_change_set(
            StackName=stack_name,
            ChangeSetName=change_set_name,
            ChangeSetType="UPDATE",
            TemplateBody=template,
            Parameters=current_parameters(cloudformation_client, stack_name),
            Capabilities=["CAPABILITY_NAMED_IAM"],
            ClientToken=token,
        )
        created = True
        cloudformation_client.get_waiter("change_set_create_complete").wait(
            StackName=stack_name,
            ChangeSetName=change_set_name,
        )
        response = cloudformation_client.describe_change_set(
            StackName=stack_name,
            ChangeSetName=change_set_name,
            IncludePropertyValues=False,
        )
    except Exception:
        if created:
            cloudformation_client.delete_change_set(
                StackName=stack_name,
                ChangeSetName=change_set_name,
            )
        raise
    changes = response.get("Changes", [])
    actual_ids = {
        item.get("ResourceChange", {}).get("LogicalResourceId") for item in changes
    }
    expected_action = "Modify" if phase in {"retain", "decouple"} else "Remove"
    expected_types = (
        {logical_id: "AWS::SSM::Parameter" for logical_id in expected_ids}
        if phase != "decouple"
        else {
            DECOUPLE_TARGETS[stack_name]["function"]: "AWS::Lambda::Function",
            DECOUPLE_TARGETS[stack_name]["role"]: "AWS::IAM::Role",
            **(
                {
                    DECOUPLE_TARGETS[stack_name]["secondary_function"]: "AWS::Lambda::Function",
                    DECOUPLE_TARGETS[stack_name]["secondary_role"]: "AWS::IAM::Role",
                }
                if "secondary_function" in DECOUPLE_TARGETS[stack_name]
                else {}
            ),
        }
    )
    if (
        response.get("Status") != "CREATE_COMPLETE"
        or response.get("ExecutionStatus") != "AVAILABLE"
        or len(changes) != len(expected_ids)
        or actual_ids != expected_ids
        or any(
            item.get("ResourceChange", {}).get("Action") != expected_action
            or item.get("ResourceChange", {}).get("ResourceType")
            != expected_types.get(item.get("ResourceChange", {}).get("LogicalResourceId"))
            for item in changes
        )
        or (phase == "retain" and any(not is_retain_policy_modification(item) for item in changes))
        or (phase == "decouple" and any(not is_direct_property_modification(item) for item in changes))
        or (phase == "detach" and any(not is_retained_removal(item) for item in changes))
    ):
        print_change_summary(changes)
        cloudformation_client.delete_change_set(
            StackName=stack_name,
            ChangeSetName=change_set_name,
        )
        raise ValueError("The Change Set is outside the approved legacy SSM scope")
    print(f"Legacy SSM {phase} Change Set is ready for {len(expected_ids)} resources.")


def self_check() -> None:
    """Exercise the string transformation without AWS access or real templates."""
    retain_change = {
        "ResourceChange": {
            "Action": "Modify",
            "Replacement": "False",
            "Scope": ["DeletionPolicy", "UpdateReplacePolicy"],
            "Details": [
                {
                    "ChangeSource": "DirectModification",
                    "Target": {
                        "Attribute": "DeletionPolicy",
                        "RequiresRecreation": "Never",
                    },
                },
                {
                    "ChangeSource": "DirectModification",
                    "Target": {
                        "Attribute": "UpdateReplacePolicy",
                        "RequiresRecreation": "Never",
                    },
                },
            ],
        }
    }
    if not is_retain_policy_modification(retain_change):
        raise ValueError("Retain Change Set guard rejected the approved shape")
    retain_change["ResourceChange"]["Replacement"] = "True"
    if is_retain_policy_modification(retain_change):
        raise ValueError("Retain Change Set guard accepted replacement")
    retain_change["ResourceChange"]["Replacement"] = "False"
    retain_change["ResourceChange"]["PolicyAction"] = "Delete"
    if is_retain_policy_modification(retain_change):
        raise ValueError("Retain Change Set guard accepted deletion")
    retain_change["ResourceChange"]["PolicyAction"] = None
    retain_change["ResourceChange"]["Scope"].append("Properties")
    if is_retain_policy_modification(retain_change):
        raise ValueError("Retain Change Set guard accepted an extra property")
    retained_removal = {"ResourceChange": {"Action": "Remove", "PolicyAction": "Retain"}}
    if not is_retained_removal(retained_removal):
        raise ValueError("Detach Change Set guard rejected Retain")
    retained_removal["ResourceChange"]["PolicyAction"] = "Delete"
    if is_retained_removal(retained_removal):
        raise ValueError("Detach Change Set guard accepted deletion")
    retained_removal["ResourceChange"]["PolicyAction"] = "Retain"
    retained_removal["ResourceChange"]["Details"] = [{}]
    if is_retained_removal(retained_removal):
        raise ValueError("Detach Change Set guard accepted a property change")
    fixture = """AWSTemplateFormatVersion: '2010-09-09'\nResources:\n  HmacSecretParameter:\n    Type: AWS::SSM::Parameter\n    Properties:\n      Name: /legacy/hmac\n  OtherResource:\n    Type: AWS::S3::Bucket\nOutputs:\n  Example:\n    Value: ok\n"""
    retained = with_retain_policies(fixture, ("HmacSecretParameter",))
    if retained.count("DeletionPolicy: Retain") != 1 or "OtherResource" not in retained:
        raise ValueError("Retain transformation is unsafe")
    detached = without_legacy_resources(retained, ("HmacSecretParameter",))
    if "HmacSecretParameter" in detached or "OtherResource" not in detached:
        raise ValueError("Detach transformation is unsafe")
    lp_legacy = "".join(
        f"  {logical_id}:\n    Type: AWS::SSM::Parameter\n    Properties:\n      Name: /legacy/{logical_id}\n"
        for logical_id in STACK_TARGETS["zer0-nyusatsu-lp-backend"]
    )
    lp_fixture = f"""AWSTemplateFormatVersion: '2010-09-09'
Resources:
{lp_legacy}  WaitlistFunctionRole:
    Type: AWS::IAM::Role
    Properties:
              - !Sub arn:aws:ssm:${{AWS::Region}}:${{AWS::AccountId}}:parameter${{LineChannelAccessTokenParameter}}
              - !Sub arn:aws:ssm:${{AWS::Region}}:${{AWS::AccountId}}:parameter${{LineChannelSecretParameter}}
              - !Sub arn:aws:ssm:${{AWS::Region}}:${{AWS::AccountId}}:parameter${{LineLiffIdParameter}}
  WaitlistFunction:
    Type: AWS::Lambda::Function
    Properties:
      Environment:
        Variables:
          LINE_CHANNEL_ACCESS_TOKEN_PARAM_NAME: !Ref LineChannelAccessTokenParameter
          LINE_CHANNEL_SECRET_PARAM_NAME: !Ref LineChannelSecretParameter
          LINE_LIFF_ID_PARAM_NAME: !Ref LineLiffIdParameter
  StripeWebhookFunctionRole:
    Type: AWS::IAM::Role
    Properties:
              - !Sub arn:aws:ssm:${{AWS::Region}}:${{AWS::AccountId}}:parameter${{StripeWebhookSecretParameter}}
  StripeWebhookFunction:
    Type: AWS::Lambda::Function
    Properties:
      Environment:
        Variables:
          STRIPE_WEBHOOK_SECRET_PARAM_NAME: !Ref StripeWebhookSecretParameter
  UnchangedResource:
    Type: AWS::S3::Bucket
Outputs:
  Example:
    Value: ok
"""
    decoupled = decouple_references(lp_fixture, "zer0-nyusatsu-lp-backend")
    assert_decouple_integrity(lp_fixture, decoupled, "zer0-nyusatsu-lp-backend")
    if any(
        re.search(rf"(?:!Ref\\s+|parameter\\$\\{{){re.escape(logical_id)}\\b", decoupled)
        for logical_id in STACK_TARGETS["zer0-nyusatsu-lp-backend"]
    ):
        raise ValueError("Decouple transformation left a legacy reference")
    print("Static legacy SSM retirement checks passed; no AWS calls were made.")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--self-check", action="store_true")
    parser.add_argument("--inspect-references", action="store_true")
    parser.add_argument("--stack-name", choices=sorted(STACK_TARGETS))
    parser.add_argument("--phase", choices=("retain", "decouple", "detach"))
    parser.add_argument(
        "--change-set-name",
        default=f"legacy-ssm-{datetime.now(timezone.utc):%Y%m%d}",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    if args.self_check:
        self_check()
        return 0
    if args.inspect_references:
        if not args.stack_name or args.phase:
            raise ValueError("inspect-references requires only an approved stack name")
        inspect_references(args.stack_name)
        return 0
    if not args.stack_name or not args.phase:
        raise ValueError("stack name and phase are required")
    create_change_set(args.stack_name, args.phase, args.change_set_name)
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as error:
        print(f"Legacy SSM Change Set was not created: {type(error).__name__}", file=sys.stderr)
        raise SystemExit(1)
