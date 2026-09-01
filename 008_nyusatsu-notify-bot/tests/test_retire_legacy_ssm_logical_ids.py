"""旧SSM論理ID整理用Change Setの安全ガードを検証する。"""

import copy
import importlib.util
from pathlib import Path


SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "retire_legacy_ssm_logical_ids.py"
SPEC = importlib.util.spec_from_file_location("retire_legacy_ssm_logical_ids", SCRIPT_PATH)
retire_legacy_ssm = importlib.util.module_from_spec(SPEC)
assert SPEC.loader is not None
SPEC.loader.exec_module(retire_legacy_ssm)


def approved_retain_change() -> dict:
    return {
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


def test_retain_guard_accepts_only_lifecycle_policies():
    assert retire_legacy_ssm.is_retain_policy_modification(approved_retain_change())

    with_extra_property = copy.deepcopy(approved_retain_change())
    with_extra_property["ResourceChange"]["Scope"].append("Properties")

    assert not retire_legacy_ssm.is_retain_policy_modification(with_extra_property)


def test_retain_guard_rejects_replacement_and_deletion():
    replacement = approved_retain_change()
    replacement["ResourceChange"]["Replacement"] = "True"
    deletion = approved_retain_change()
    deletion["ResourceChange"]["PolicyAction"] = "Delete"

    assert not retire_legacy_ssm.is_retain_policy_modification(replacement)
    assert not retire_legacy_ssm.is_retain_policy_modification(deletion)


def test_detach_guard_requires_retained_stack_record_removal():
    approved = {"ResourceChange": {"Action": "Remove", "PolicyAction": "Retain"}}
    deletion = {"ResourceChange": {"Action": "Remove", "PolicyAction": "Delete"}}
    with_details = {
        "ResourceChange": {
            "Action": "Remove",
            "PolicyAction": "Retain",
            "Details": [{}],
        }
    }

    assert retire_legacy_ssm.is_retained_removal(approved)
    assert not retire_legacy_ssm.is_retained_removal(deletion)
    assert not retire_legacy_ssm.is_retained_removal(with_details)


def test_stack_parameters_are_reused_without_reading_values():
    class FakeCloudFormation:
        def describe_stacks(self, StackName):
            assert StackName == "zer0-nyusatsu-lp-backend"
            return {
                "Stacks": [
                    {
                        "Parameters": [
                            {"ParameterKey": "AllowedOrigin", "ParameterValue": "REDACTED"},
                            {"ParameterKey": "LogRetentionDays", "ParameterValue": "14"},
                        ]
                    }
                ]
            }

    assert retire_legacy_ssm.current_parameters(
        FakeCloudFormation(), "zer0-nyusatsu-lp-backend"
    ) == [
        {"ParameterKey": "AllowedOrigin", "UsePreviousValue": True},
        {"ParameterKey": "LogRetentionDays", "UsePreviousValue": True},
    ]
