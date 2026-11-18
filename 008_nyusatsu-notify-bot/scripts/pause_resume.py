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

テンプレートはローカルの次の2ファイルを使う（get-template はASCII以外を「??」で返すため、
本番から取り出したものを当てると本番の日本語が「??」で上書きされる。2026-11-18に一度起きて復元済み）。
    - infra/cfn-nyusatsu-notify-bot-production.yaml（本番に入っている2026-08-09版の写し。
      隣の cfn-nyusatsu-notify-bot.yaml は本番未適用の新しい版なので使わない）
    - lp/infra/cfn-lp-hosting.yaml

当てる前に、ローカルのファイルと本番のテンプレートが一致することを確かめる
（ASCII以外の文字は「?」に置き換え、コメント行・空行と切り替える行の値は比べない）。
一致しなければ止まる。実行後は、切り替えた値をローカルのファイルにも書き戻す。
変更セットに対象以外の変更が1つでも含まれていれば、実行せずに削除して止まる。
"""

import argparse
import re
import sys
import time
from pathlib import Path

import boto3

REGION = "ap-northeast-1"
NOTIFY_STACK = "zer0-nyusatsu-notify-bot"
LP_STACK = "zer0-nyusatsu-lp-hosting"
RULE_NAME = "zer0-nyusatsu-daily-schedule"

cfn = boto3.client("cloudformation", region_name=REGION)
events = boto3.client("events", region_name=REGION)
PROJECT_DIR = Path(__file__).resolve().parent.parent
NOTIFY_TEMPLATE = PROJECT_DIR / "infra" / "cfn-nyusatsu-notify-bot-production.yaml"
LP_TEMPLATE = PROJECT_DIR / "lp" / "infra" / "cfn-lp-hosting.yaml"


def comparable(lines, block_name, key):
    """比較用に、コメント行・空行を除き、ASCII以外を「?」にし、切り替える行の値を伏せる。"""
    out = []
    in_block = False
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"  \S", line):
            in_block = line == f"  {block_name}:"
        if in_block and re.match(rf"\s+{key}: \S+$", line):
            line = re.sub(rf"({key}): \S+$", r"\1: <toggle>", line)
        out.append("".join("?" if ord(c) > 127 else c for c in line.rstrip()))
    return out


def load_local_matching(stack, path, block_name, key):
    """ローカルのテンプレートを読み、本番と一致することを確かめてから行のリストで返す。"""
    local = path.read_text(encoding="utf-8").replace("\r", "").split("\n")
    deployed = cfn.get_template(StackName=stack, TemplateStage="Original")["TemplateBody"]
    deployed = deployed.replace("\r", "").split("\n")
    if comparable(local, block_name, key) != comparable(deployed, block_name, key):
        raise RuntimeError(f"{path} が本番 {stack} のテンプレートと一致しない。差分を確かめてから使うこと")
    return local


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


def make_change_set(stack, body, name, expected_logical_id, expected_path):
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
        raise RuntimeError(f"{stack} の変更セット作成に失敗: {cs.get('StatusReason')}")
    # Add/Remove/ImportのようにDetailsが空の変更も見落とさないよう、ResourceChange単位で数える。
    resource_changes = [c["ResourceChange"] for c in cs["Changes"]]
    details = []
    for rc in resource_changes:
        print(f"[{stack}] {rc['LogicalResourceId']} {rc['Action']} Replacement={rc.get('Replacement')}")
        for d in rc.get("Details", []):
            t = d["Target"]
            details.append((rc["LogicalResourceId"], t.get("Path")))
            print(f"[{stack}]   {t.get('Path')}: {t.get('BeforeValue')} -> {t.get('AfterValue')}")
    ok = (
        len(resource_changes) == 1
        and resource_changes[0]["LogicalResourceId"] == expected_logical_id
        and resource_changes[0]["Action"] == "Modify"
        and resource_changes[0].get("Replacement") == "False"
        and details
        and all(d == (expected_logical_id, expected_path) for d in details)
    )
    if not ok:
        cfn.delete_change_set(StackName=stack, ChangeSetName=name)
        raise RuntimeError(f"{stack} に想定外の変更が含まれるため中止（この変更セットは削除済み）")
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

    try:
        notify = load_local_matching(NOTIFY_STACK, NOTIFY_TEMPLATE, "DailyScheduleRule", "State")
        lp = load_local_matching(LP_STACK, LP_TEMPLATE, "LpDistribution", "Enabled")
    except RuntimeError as exc:
        sys.exit(f"[error] {exc}")
    notify = set_in_block(notify, "DailyScheduleRule", "State", "ENABLED" if resume else "DISABLED")
    lp = set_in_block(lp, "LpDistribution", "Enabled", "true" if resume else "false")

    targets = []

    def cleanup():
        # 途中で止まったときに、作成済みで未実行の変更セットを残さない。
        for stack, cs in targets:
            try:
                cfn.delete_change_set(StackName=stack, ChangeSetName=cs)
            except Exception:
                pass

    try:
        name = f"{args.action}-schedule-{suffix}"
        if make_change_set(NOTIFY_STACK, "\n".join(notify), name, "DailyScheduleRule", "/Properties/State"):
            targets.append((NOTIFY_STACK, name))
        name = f"{args.action}-lp-{suffix}"
        if make_change_set(LP_STACK, "\n".join(lp), name, "LpDistribution",
                           "/Properties/DistributionConfig/Enabled"):
            targets.append((LP_STACK, name))
    except Exception as exc:
        cleanup()
        sys.exit(f"[error] {exc}")

    if not args.execute:
        cleanup()
        print("確認のみで終了（変更セットは削除済み）。実行するには --execute を付ける")
        return
    local_files = {NOTIFY_STACK: (NOTIFY_TEMPLATE, notify), LP_STACK: (LP_TEMPLATE, lp)}
    while targets:
        stack, cs = targets[0]
        try:
            execute(stack, cs)
        except Exception as exc:
            cleanup()
            sys.exit(f"[error] {stack} の実行で失敗: {exc}（未実行の変更セットは削除済み）")
        # 本番に当てた内容をローカルにも書き戻し、次回の一致確認が通るようにする。
        path, lines = local_files[stack]
        path.write_text("\n".join(lines), encoding="utf-8")
        targets.pop(0)
    status()


if __name__ == "__main__":
    main()
