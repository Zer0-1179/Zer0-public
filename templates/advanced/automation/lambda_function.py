"""
CloudWatch Alarm Auto-Updater

Automatically updates CloudWatch Alarm dimensions when an EC2 instance or FSx
file system is restored (from AMI / snapshot), so alarms keep tracking the
correct resource without manual intervention.

Trigger events:
  - aws.ec2 / EC2 Instance State-change Notification  (state: running)
  - aws.fsx / FSx File System Lifecycle Change        (lifecycle: AVAILABLE)

Tag usage:
  EC2 / FSx  — CWAlarmAutoUpdate=<identifier>   (e.g. "web-server-01")
  CW Alarm   — CWAlarmAutoUpdate=<identifier>   (same value)

  The identifier can be any unique string. When EC2 starts, Lambda finds all
  CloudWatch Alarms sharing the same tag value and updates their dimensions to
  the new resource ID. No alarm naming convention required.

The tag key defaults to "CWAlarmAutoUpdate" and can be overridden with the
ENABLE_TAG_KEY environment variable.
"""

import json
import logging
import os
import boto3

logger = logging.getLogger(__name__)
logger.setLevel(getattr(logging, os.environ.get('LOG_LEVEL', 'INFO').upper(), logging.INFO))

ENABLE_TAG_KEY = os.environ.get('ENABLE_TAG_KEY', 'CWAlarmAutoUpdate')


def get_tag(tags: list[dict], key: str) -> str | None:
    """Return the value of the specified tag key, or None if not present."""
    return next((t['Value'] for t in tags if t['Key'] == key), None)


def get_identifier(tags: list[dict]) -> str | None:
    """Return the ENABLE_TAG_KEY value if present and non-empty, else None."""
    return get_tag(tags, ENABLE_TAG_KEY) or None


def fetch_ec2_tags(instance_id: str) -> list[dict]:
    """Return all tags of an EC2 instance."""
    ec2 = boto3.client('ec2')
    response = ec2.describe_instances(InstanceIds=[instance_id])
    return response['Reservations'][0]['Instances'][0].get('Tags', [])


def fetch_fsx_tags(file_system_id: str) -> list[dict]:
    """Return all tags of an FSx file system."""
    fsx = boto3.client('fsx')
    response = fsx.describe_file_systems(FileSystemIds=[file_system_id])
    return response['FileSystems'][0].get('Tags', [])


def find_alarm_names_by_tag(identifier: str) -> list[str]:
    """
    Return names of CloudWatch alarms tagged with ENABLE_TAG_KEY=identifier.

    Uses the Resource Groups Tagging API so alarm names can be anything.
    """
    rgt = boto3.client('resourcegroupstaggingapi')
    paginator = rgt.get_paginator('get_resources')
    names = []
    for page in paginator.paginate(
        TagFilters=[{'Key': ENABLE_TAG_KEY, 'Values': [identifier]}],
        ResourceTypeFilters=['cloudwatch:alarm'],
    ):
        for resource in page['ResourceTagMappingList']:
            # arn:aws:cloudwatch:{region}:{account}:alarm:{name}
            names.append(resource['ResourceARN'].split(':alarm:')[-1])
    return names


def build_put_params(alarm: dict, dim_name: str, new_id: str) -> dict:
    """
    Build put_metric_alarm parameters from an existing alarm,
    replacing the specified dimension value with new_id.
    """
    updated_dims = [
        {'Name': d['Name'], 'Value': new_id if d['Name'] == dim_name else d['Value']}
        for d in alarm.get('Dimensions', [])
    ]

    params = {
        'AlarmName':               alarm['AlarmName'],
        'ActionsEnabled':          alarm.get('ActionsEnabled', True),
        'OKActions':               alarm.get('OKActions', []),
        'AlarmActions':            alarm.get('AlarmActions', []),
        'InsufficientDataActions': alarm.get('InsufficientDataActions', []),
        'MetricName':              alarm['MetricName'],
        'Namespace':               alarm['Namespace'],
        'Dimensions':              updated_dims,
        'Period':                  alarm['Period'],
        'EvaluationPeriods':       alarm['EvaluationPeriods'],
        'Threshold':               alarm['Threshold'],
        'ComparisonOperator':      alarm['ComparisonOperator'],
        'TreatMissingData':        alarm.get('TreatMissingData', 'missing'),
    }

    # Statistic and ExtendedStatistic are mutually exclusive in the API
    if 'Statistic' in alarm:
        params['Statistic'] = alarm['Statistic']
    elif 'ExtendedStatistic' in alarm:
        params['ExtendedStatistic'] = alarm['ExtendedStatistic']

    for key in ['AlarmDescription', 'DatapointsToAlarm', 'Unit', 'EvaluateLowSampleCountPercentile']:
        if alarm.get(key) is not None:
            params[key] = alarm[key]

    return params


def update_alarms(new_id: str, alarm_names: list[str], dim_name: str) -> tuple[int, int]:
    """
    Update dimension dim_name to new_id on each alarm in alarm_names.

    Returns (updated_count, skipped_count).
    """
    if not alarm_names:
        return 0, 0

    cw = boto3.client('cloudwatch')
    updated = skipped = 0

    response = cw.describe_alarms(AlarmNames=alarm_names, AlarmTypes=['MetricAlarm'])
    for alarm in response['MetricAlarms']:

        # Skip expression-based alarms (Metrics Insights / metric math)
        if alarm.get('Metrics'):
            skipped += 1
            continue

        dims = alarm.get('Dimensions', [])
        current_id = next((d['Value'] for d in dims if d['Name'] == dim_name), None)
        if not current_id:
            logger.debug('SKIP %s: no %s dimension', alarm['AlarmName'], dim_name)
            continue

        # Already pointing to the restored resource — normal restart, not a restore
        if current_id == new_id:
            logger.info('SKIP %s: already up-to-date (%s)', alarm['AlarmName'], new_id)
            skipped += 1
            continue

        cw.put_metric_alarm(**build_put_params(alarm, dim_name, new_id))
        logger.info('UPDATE %s: %s %s -> %s', alarm['AlarmName'], dim_name, current_id, new_id)
        updated += 1

    return updated, skipped


# Dispatch table — add entries here to support additional resource types
_SOURCES = {
    'aws.ec2': {
        'state_key':   'state',
        'state_val':   'running',
        'id_key':      'instance-id',
        'fetch_tags':  fetch_ec2_tags,
        'dim_name':    'InstanceId',
        'skip_reason': 'not running state',
    },
    'aws.fsx': {
        'state_key':   'lifecycle',
        'state_val':   'AVAILABLE',
        'id_key':      'file-system-id',
        'fetch_tags':  fetch_fsx_tags,
        'dim_name':    'FileSystemId',
        'skip_reason': 'not AVAILABLE lifecycle',
    },
}


def handler(event: dict, context) -> dict:
    logger.info(json.dumps(event, default=str))

    source = event.get('source')
    config = _SOURCES.get(source)
    if not config:
        logger.warning('Unhandled event source: %s', source)
        return {'status': 'unknown_source'}

    detail = event.get('detail', {})
    resource_id = detail.get(config['id_key'])
    if detail.get(config['state_key']) != config['state_val'] or not resource_id:
        return {'status': 'skipped', 'reason': config['skip_reason']}

    tags = config['fetch_tags'](resource_id)
    identifier = get_identifier(tags)
    if not identifier:
        logger.info('SKIP %s: no %s tag', resource_id, ENABLE_TAG_KEY)
        return {'status': 'skipped', 'reason': 'no_enable_tag'}

    alarm_names = find_alarm_names_by_tag(identifier)
    if not alarm_names:
        logger.info('No alarms tagged with %s=%s', ENABLE_TAG_KEY, identifier)

    updated, skipped = update_alarms(resource_id, alarm_names, config['dim_name'])
    result = {'status': 'success', 'updated': updated, 'skipped': skipped}
    logger.info(json.dumps(result))
    return result
