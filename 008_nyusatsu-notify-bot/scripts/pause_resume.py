#!/usr/bin/env python3
"""008 入札情報ウォッチの一時停止・再開を切り替える。

使い方:
    python3 scripts/pause_resume.py status
    python3 scripts/pause_resume.py resume            # 変更セットを作って中身を確認するだけ（実行しない）
    python3 scripts/pause_resume.py resume --execute  # 確認した内容で実行する
    python3 scripts/pause_resume.py pause [--execute]

切り替えるのは次の2か所だけ。Lambda・DynamoDB・SES・SSM・S3には触れない。
    - zer0-nyusatsu-notify-bot  の DailyScheduleRule.State（ENABLED / DISABLED）
    - zer0-nyusatsu-lp-hosting  の LpDistribution.DistributionConfig.Enabled（true / false）

ローカルの infra/cfn-nyusatsu-notify-bot.yaml は本番スタックより新しい版（S3 artifact方式・
SSMパス直書き）で、本番には未適用。ローカル版をそのまま当てると想定外の変更が混ざるため、
このスクリプトは「本番に今入っているテンプレート」を取り出し、対象の1行だけを書き換えて当てる。

本番から取り出したテンプレートは日本語が「??」に化けて返るため、Lambda・EventBridge・
CloudWatch Alarmの説明文を実リソースの値で埋め戻してから変更セットを作る。
変更セットに対象以外の変更が1つでも含まれていれば、実行せずに削除して止まる。
"""

import argparse
import re
import sys
import time

import boto3

REGION = "ap-northeast-1"
NOTIFY_STACK = "zer0-nyusatsu-notify-bot"
LP_STACK = "zer0-nyusatsu-lp-hosting"
RULE_NAME = "zer0-nyusatsu-daily-schedule"

cfn = boto3.client("cloudformation", region_name=REGION)
lam = boto3.client("lambda", region_name=REGION)
events = boto3.client("events", region_name=REGION)
cw = boto3.client("cloudwatch", region_name=REGION)


def live_description(name):
    """リソース名から実リソースの説明文を取得する。該当しなければNone。"""
    try:
        return lam.get_function_configuration(FunctionName=name).get("Description")
    except lam.exceptions.ResourceNotFoundException:
        pass
    try:
        return events.describe_rule(Name=name).get("Description")
    except events.exceptions.ResourceNotFoundException:
        pass
    alarms = cw.describe_alarms(AlarmNames=[name])["MetricAlarms"]
    if alarms:
        return alarms[0].get("AlarmDescription")
    return None


def restore_garbled_descriptions(lines):
    """「??」に化けた説明文を、直前のリソース名に対応する実リソースの値で置き換える。"""
    current = None
    for i, line in enumerate(lines):
        m = re.match(r"\s+(?:FunctionName|Name|AlarmName): (\S+)$", line)
        if m:
            current = m.group(1)
            continue
        m = re.match(r"(\s+)(Description|AlarmDescription): (.*)$", line)
        if m and current and "??" in m.group(3):
            value = live_description(current)
            if value is None:
                sys.exit(f"[error] {current} の実リソースの説明文を取得できない")
            lines[i] = f'{m.group(1)}{m.group(2)}: "{value}"'
            current = None
    return lines


def set_in_block(lines, block_name, key, value):
    """`  block_name:` の配下で最初に現れる `key:` 行の値を書き換える。"""
    start = next(i for i, l in enumerate(lines) if l == f"  {block_name}:")
    for i in range(start + 1, len(lines)):
        if re.match(r"  \S", lines[i]):  # 次のリソースに入ったら打ち切り
            break
        m = re.match(rf"(\s+){key}: \S+$", lines[i])
        if m:
            lines[i] = f"{m.group(1)}{key}: {value}"
            return lines
    sys.exit(f"[error] {block_name} の {key} が見つからない")


def deployed_template(stack):
    return cfn.get_template(StackName=stack, TemplateStage="Original")["TemplateBody"]


def make_change_set(stack, body, name, expected_logical_id, expected_property):
    params = [
        {"ParameterKey": p["ParameterKey"], "UsePreviousValue": True}
        for p in cfn.describe_stacks(StackName=stack)["Stacks"][0].get("Parameters", [])
    ]
    cfn.create_change_set(
        StackName=stack,
        ChangeSetName=name,
        TemplateBody=body,
        Parameters=params,
        Capabilities=["CAPABILITY_NAMED_IAM"],
    )
    while True:
        cs = cfn.describe_change_set(StackName=stack, ChangeSetName=name, IncludePropertyValues=True)
        if cs["Status"] in ("CREATE_COMPLETE", "FAILED"):
            break
        time.sleep(3)
    if cs["Status"] == "FAILED":
        cfn.delete_change_set(StackName=stack, ChangeSetName=name)
        if "didn't contain changes" in cs.get("StatusReason", ""):
            print(f"[{stack}] 既に目的の状態（変更なし）")
            return False
        sys.exit(f"[error] {stack} の変更セット作成に失敗: {cs.get('StatusReason')}")
    changes = []
    for c in cs["Changes"]:
        rc = c["ResourceChange"]
        for d in rc.get("Details", []):
            t = d["Target"]
            changes.append((rc["LogicalResourceId"], rc["Action"], rc.get("Replacement"),
                            t.get("Name"), t.get("BeforeValue"), t.get("AfterValue")))
    for ch in changes:
        print(f"[{stack}] {ch}")
    unexpected = [
        ch for ch in changes
        if not (ch[0] == expected_logical_id and ch[1] == "Modify" and ch[2] == "False"
                and ch[3] == expected_property)
    ]
    if unexpected or not changes:
        cfn.delete_change_set(StackName=stack, ChangeSetName=name)
        sys.exit(f"[error] {stack} に想定外の変更が含まれるため中止（変更セットは削除済み）")
    return True


def execute(stack, name):
    cfn.execute_change_set(StackName=stack, ChangeSetName=name)
    cfn.get_waiter("stack_update_complete").wait(
        StackName=stack, WaiterConfig={"Delay": 15, "MaxAttempts": 120}
    )
    print(f"[{stack}] UPDATE_COMPLETE")


def lp_distribution_id():
    for r in cfn.describe_stack_resources(StackName=LP_STACK)["StackResources"]:
        if r["LogicalResourceId"] == "LpDistribution":
            return r["PhysicalResourceId"]
    sys.exit("[error] LpDistribution が見つからない")


def status():
    cf = boto3.client("cloudfront")
    dist = cf.get_distribution(Id=lp_distribution_id())["Distribution"]
    print(f"収集スケジュール {RULE_NAME}: {events.describe_rule(Name=RULE_NAME)['State']}")
    print(f"LP CloudFront: Enabled={dist['DistributionConfig']['Enabled']} Status={dist['Status']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("action", choices=["status", "pause", "resume"])
    ap.add_argument("--execute", action="store_true", help="変更セットを実行する（省略時は確認のみ）")
    args = ap.parse_args()
    if args.action == "status":
        status()
        return

    resume = args.action == "resume"
    suffix = time.strftime("%Y%m%d%H%M%S")

    notify = restore_garbled_descriptions(deployed_template(NOTIFY_STACK).split("\n"))
    notify = set_in_block(notify, "DailyScheduleRule", "State", "ENABLED" if resume else "DISABLED")
    lp = deployed_template(LP_STACK).split("\n")
    lp = set_in_block(lp, "LpDistribution", "Enabled", "true" if resume else "false")

    targets = []
    name = f"{args.action}-schedule-{suffix}"
    if make_change_set(NOTIFY_STACK, "\n".join(notify), name, "DailyScheduleRule", "State"):
        targets.append((NOTIFY_STACK, name))
    name = f"{args.action}-lp-{suffix}"
    if make_change_set(LP_STACK, "\n".join(lp), name, "LpDistribution", "DistributionConfig"):
        targets.append((LP_STACK, name))

    if not args.execute:
        for stack, cs in targets:
            cfn.delete_change_set(StackName=stack, ChangeSetName=cs)
        print("確認のみで終了（変更セットは削除済み）。実行するには --execute を付ける")
        return
    for stack, cs in targets:
        execute(stack, cs)
    status()


if __name__ == "__main__":
    main()
