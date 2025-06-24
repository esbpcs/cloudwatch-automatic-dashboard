import boto3
import json
import os
from botocore.exceptions import ClientError
from botocore.config import Config

retry_config = Config(retries={"max_attempts": 5, "mode": "standard"})

ec2_client = boto3.client("ec2", config=retry_config)
cloudwatch_client = boto3.client("cloudwatch", config=retry_config)

SERVICE_CONFIG = {
    "ec2_instance": {
        "filter": "ec2:instance",
        "id": "instance/",
        "builder": "create_ec2_hybrid_widget",
    },
    "rds_instance": {
        "filter": "rds:db",
        "id": ":db:",
        "builder": "create_rds_detailed_widget",
    },
    "lambda_function": {
        "filter": "lambda:function",
        "id": ":function:",
        "builder": "create_lambda_widget",
    },
    "alb": {
        "filter": "elasticloadbalancing:loadbalancer",
        "id": "loadbalancer/app",
        "builder": "create_alb_widget",
    },
    "nlb": {
        "filter": "elasticloadbalancing:loadbalancer",
        "id": "loadbalancer/net",
        "builder": "create_nlb_widget",
    },
    "classic_elb": {
        "filter": "elasticloadbalancing:loadbalancer",
        "id": ":",
        "builder": "create_classic_elb_widget",
    },
    "ecs_service": {
        "filter": "ecs:service",
        "id": "service/",
        "builder": "create_ecs_widget",
    },
    "dynamodb_table": {
        "filter": "dynamodb:table",
        "id": "table/",
        "builder": "create_dynamodb_widget",
    },
    "redshift_cluster": {
        "filter": "redshift:cluster",
        "id": ":cluster:",
        "builder": "create_redshift_widget",
    },
    "sqs_queue": {
        "filter": "sqs",
        "id": "arn:aws:sqs:",
        "builder": "create_sqs_widget",
    },
    "sns_topic": {
        "filter": "sns",
        "id": "arn:aws:sns:",
        "builder": "create_sns_widget",
    },
    "cloudfront_distribution": {
        "filter": "cloudfront:distribution",
        "id": "distribution/",
        "builder": "create_cloudfront_widget",
        "is_global": True,
    },
    "route53_healthcheck": {
        "filter": "route53:healthcheck",
        "id": "healthcheck/",
        "builder": "create_route53_widget",
        "is_global": True,
    },
    "acm_certificate": {
        "filter": "acm:certificate",
        "id": "certificate/",
        "builder": "create_acm_widget",
        "is_global": True,
    },
    "elasticache_cluster": {
        "filter": "elasticache:cluster",
        "id": ":cluster:",
        "builder": "create_elasticache_widget",
    },
    "fsx_filesystem": {
        "filter": "fsx:filesystem",
        "id": "filesystem/",
        "builder": "create_fsx_widget",
    },
    "storage_gateway": {
        "filter": "storagegateway:gateway",
        "id": "gateway/",
        "builder": "create_storagegateway_widget",
    },
    "dx_connection": {
        "filter": "directconnect:dxcon",
        "id": "dxcon/",
        "builder": "create_dx_widget",
    },
    "vpn_connection": {
        "filter": "ec2:vpn-connection",
        "id": "vpn-",
        "builder": "create_vpn_widget",
    },
}


def lambda_handler(event, context):
    region = os.environ["AWS_REGION"]
    dashboard_name = os.environ["DASHBOARD_NAME"]
    tag_key = os.environ["TAG_KEY"]
    tag_value = os.environ["TAG_VALUE"]
    slo_target = float(os.environ["SLO_TARGET"])
    print(f"Starting dashboard update for '{dashboard_name}'...")
    tagged_resources = get_tagged_resources(tag_key, tag_value)
    if not tagged_resources:
        print("No tagged resources found. Creating an empty dashboard placeholder.")
        update_dashboard(
            dashboard_name,
            [
                {
                    "type": "text",
                    "x": 0,
                    "y": 0,
                    "width": 24,
                    "height": 2,
                    "properties": {
                        "markdown": f"# No resources found with tag: `{tag_key}:{tag_value}`"
                    },
                }
            ],
        )
        return {"statusCode": 200, "body": "No tagged resources found."}
    all_widgets, y_pos = [], 0
    print("Creating aggregate SLO widgets...")
    slo_resources = {
        "alb": [r for r in tagged_resources if "loadbalancer/app" in r["ResourceARN"]],
        "lambda": [r for r in tagged_resources if ":function:" in r["ResourceARN"]],
        "cloudfront": [
            r for r in tagged_resources if "distribution/" in r["ResourceARN"]
        ],
    }
    if slo_resources["alb"]:
        all_widgets.extend(
            create_aggregate_alb_slo_widget(
                slo_resources["alb"], region, y_pos, slo_target
            )
        )
        y_pos += 6
    if slo_resources["lambda"]:
        all_widgets.extend(
            create_aggregate_lambda_slo_widget(
                slo_resources["lambda"], region, y_pos, slo_target
            )
        )
        y_pos += 6
    if slo_resources["cloudfront"]:
        all_widgets.extend(
            create_aggregate_cloudfront_slo_widget(
                slo_resources["cloudfront"], region, y_pos, slo_target
            )
        )
        y_pos += 6
    if all_widgets:
        all_widgets.append(
            {
                "type": "text",
                "x": 0,
                "y": y_pos,
                "width": 24,
                "height": 1,
                "properties": {
                    "markdown": "--- \n ### **Individual Resource Metrics**"
                },
            }
        )
        y_pos += 1
    print("Creating individual resource health widgets...")
    sorted_resources = sorted(tagged_resources, key=lambda r: r["ResourceARN"])
    for resource in sorted_resources:
        arn = resource["ResourceARN"]
        matched_configs = [c for c in SERVICE_CONFIG.values() if c["id"] in arn]
        if not matched_configs:
            continue
        best_match_config = max(matched_configs, key=lambda c: len(c["id"]))
        try:
            is_global = best_match_config.get("is_global", False)
            widget_func = globals()[best_match_config["builder"]]
            if (
                best_match_config["builder"] == "create_classic_elb_widget"
                and "loadbalancer/" in arn
            ):
                continue
            widget = widget_func(arn, region if not is_global else "us-east-1", y_pos)
            if widget:
                all_widgets.append(widget)
                y_pos += 8
        except Exception as e:
            print(
                f"ERROR: Could not create widget for ARN {arn}. Builder: {best_match_config['builder']}. Details: {e}"
            )
    update_dashboard(dashboard_name, all_widgets)
    return {
        "statusCode": 200,
        "body": f"Dashboard updated successfully with {len(all_widgets)} widgets.",
    }


def get_tagged_resources(tag_key, tag_value):
    tagging_client = boto3.client("resourcegroupstaggingapi", config=retry_config)
    resources, token = [], ""
    filters = list(set([svc["filter"] for svc in SERVICE_CONFIG.values()]))
    while True:
        try:
            response = tagging_client.get_resources(
                TagFilters=[{"Key": tag_key, "Values": [tag_value]}],
                ResourceTypeFilters=filters,
                PaginationToken=token,
            )
            resources.extend(response["ResourceTagMappingList"])
            token = response.get("PaginationToken", "")
            if not token:
                break
        except ClientError as e:
            print(f"FATAL: Could not call get_resources API: {e}")
            return []
    return resources


def update_dashboard(dashboard_name, widgets):
    try:
        cloudwatch_client.put_dashboard(
            DashboardName=dashboard_name, DashboardBody=json.dumps({"widgets": widgets})
        )
        print(f"SUCCESS: Dashboard '{dashboard_name}' was updated.")
    except ClientError as e:
        print(f"FATAL: Could not update dashboard '{dashboard_name}': {e}")


def create_aggregate_alb_slo_widget(resources, region, y, slo_target):
    metrics = []
    for i, res in enumerate(resources):
        lb_name = "/".join(res["ResourceARN"].split("/")[-3:])
        metrics.extend(
            [
                {
                    "id": f"r{i}",
                    "visible": False,
                    "expression": f"SEARCH('{{AWS/ApplicationELB,LoadBalancer}}MetricName=\"RequestCount\" \"{lb_name}\"' ,'Sum',300)",
                },
                {
                    "id": f"e{i}",
                    "visible": False,
                    "expression": f"SEARCH('{{AWS/ApplicationELB,LoadBalancer}}MetricName=\"HTTPCode_Target_5XX_Count\" \"{lb_name}\"' ,'Sum',300)",
                },
            ]
        )
    total_requests_expression = f"SUM([r{i} for i in range(len(resources))])"
    total_errors_expression = f"SUM([e{i} for i in range(len(resources))])"
    metrics.append(
        {
            "id": "slo",
            "expression": f"100*(1-{total_errors_expression}/{total_requests_expression})",
            "label": "Availability %",
        }
    )
    slo_graph = {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 18,
        "height": 6,
        "properties": {
            "metrics": metrics,
            "view": "timeSeries",
            "region": region,
            "title": "Application Load Balancer (ALB) Availability SLO",
            "yAxis": {"left": {"min": 95, "max": 100}},
            "annotations": {
                "horizontal": [
                    {
                        "color": "#ff0000",
                        "label": f"SLO Target ({slo_target}%)",
                        "value": slo_target,
                    }
                ]
            },
        },
    }
    slo_value = {
        "type": "metric",
        "x": 18,
        "y": y,
        "width": 6,
        "height": 6,
        "properties": {
            "metrics": [["..."]],
            "view": "singleValue",
            "region": region,
            "title": "Current Availability",
        },
    }
    return [slo_graph, slo_value]


def create_aggregate_lambda_slo_widget(resources, region, y, slo_target):
    search_expression = " OR ".join(
        [
            f'"{name}"'
            for name in [res["ResourceARN"].split(":")[-1] for res in resources]
        ]
    )
    metrics = [
        {
            "id": "invocations",
            "expression": f"SEARCH('{{AWS/Lambda,FunctionName}}MetricName=\"Invocations\"({search_expression})','Sum',300)",
            "visible": False,
        },
        {
            "id": "errors",
            "expression": f"SEARCH('{{AWS/Lambda,FunctionName}}MetricName=\"Errors\"({search_expression})','Sum',300)",
            "visible": False,
        },
        {
            "id": "slo",
            "expression": "100*(invocations-errors)/invocations",
            "label": "Success Rate %",
        },
    ]
    slo_graph = {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 18,
        "height": 6,
        "properties": {
            "metrics": metrics,
            "view": "timeSeries",
            "region": region,
            "title": "Lambda Function Success Rate SLO",
            "yAxis": {"left": {"min": 95, "max": 100}},
            "annotations": {
                "horizontal": [
                    {
                        "color": "#ff0000",
                        "label": f"SLO Target ({slo_target}%)",
                        "value": slo_target,
                    }
                ]
            },
        },
    }
    slo_value = {
        "type": "metric",
        "x": 18,
        "y": y,
        "width": 6,
        "height": 6,
        "properties": {
            "metrics": [["..."]],
            "view": "singleValue",
            "region": region,
            "title": "Current Success Rate",
        },
    }
    return [slo_graph, slo_value]


def create_aggregate_cloudfront_slo_widget(resources, region, y, slo_target):
    search_expression = " OR ".join(
        [
            f'"{dist_id}"'
            for dist_id in [res["ResourceARN"].split("/")[-1] for res in resources]
        ]
    )
    metrics = [
        {
            "id": "error_rate",
            "expression": f"SEARCH('{{AWS/CloudFront,DistributionId,Region}}MetricName=\"5xxErrorRate\"Region=\"Global\"({search_expression})','Average',300)",
            "visible": False,
        },
        {"id": "slo", "expression": "100-error_rate", "label": "Success Rate %"},
    ]
    slo_graph = {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 18,
        "height": 6,
        "properties": {
            "metrics": metrics,
            "view": "timeSeries",
            "region": region,
            "title": "CloudFront Success Rate SLO",
            "yAxis": {"left": {"min": 95, "max": 100}},
            "annotations": {
                "horizontal": [
                    {
                        "color": "#ff0000",
                        "label": f"SLO Target ({slo_target}%)",
                        "value": slo_target,
                    }
                ]
            },
        },
    }
    slo_value = {
        "type": "metric",
        "x": 18,
        "y": y,
        "width": 6,
        "height": 6,
        "properties": {
            "metrics": [["..."]],
            "view": "singleValue",
            "region": region,
            "title": "Current Success Rate",
        },
    }
    return [slo_graph, slo_value]


def create_ec2_hybrid_widget(arn, region, y):
    instance_id = arn.split("/")[-1]
    try:
        response = ec2_client.describe_instances(InstanceIds=[instance_id])
        platform = response["Reservations"][0]["Instances"][0].get("Platform", "linux")
    except ClientError as e:
        print(
            f"WARN: Could not describe instance {instance_id}, falling back to standard widget. Error: {e}"
        )
        return create_standard_ec2_widget(instance_id, region, y, "Unknown OS")
    agent_metric_name = (
        "% Committed Bytes In Use" if platform == "windows" else "mem_used_percent"
    )
    agent_metrics_exist = False
    try:
        metrics_response = cloudwatch_client.list_metrics(
            Namespace="CWAgent",
            MetricName=agent_metric_name,
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        )
        if metrics_response.get("Metrics"):
            agent_metrics_exist = True
    except ClientError:
        pass
    if agent_metrics_exist:
        print(f"INFO: CWAgent metrics found for {platform} instance {instance_id}.")
        return (
            create_windows_agent_widget(instance_id, region, y)
            if platform == "windows"
            else create_linux_agent_widget(instance_id, region, y)
        )
    else:
        print(
            f"INFO: CWAgent metrics not found for {instance_id}. Building standard agentless widget."
        )
        return create_standard_ec2_widget(instance_id, region, y, platform.capitalize())


def create_windows_agent_widget(instance_id, region, y):
    title = f"EC2 Detailed (Agent): {instance_id} (Windows)"
    metrics = [
        [{"expression": "100 - m1", "label": "CPU Usage %", "id": "e1"}],
        [
            "CWAgent",
            "% Idle Time",
            "InstanceId",
            instance_id,
            "CustomDimensionName",
            "CPUMetric",
            {"id": "m1", "visible": False},
        ],
        [
            "...",
            "% Committed Bytes In Use",
            "InstanceId",
            instance_id,
            "CustomDimensionName",
            "MEMMetric",
            {"label": "Memory Usage %"},
        ],
    ]
    try:
        disk_metrics_response = cloudwatch_client.list_metrics(
            Namespace="CWAgent",
            MetricName="% Free Space",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        )
        discovered_drives = set(
            dim["Value"]
            for metric in disk_metrics_response.get("Metrics", [])
            for dim in metric.get("Dimensions", [])
            if dim["Name"] == "LogicalDisk"
        )
        print(f"INFO: Discovered drives for {instance_id}: {list(discovered_drives)}")
        for drive in sorted(list(discovered_drives)):
            metrics.append(
                [
                    "...",
                    "% Free Space",
                    "LogicalDisk",
                    drive,
                    "InstanceId",
                    instance_id,
                    "CustomDimensionName",
                    "DISKMetric",
                    {"label": f"Disk Free % ({drive})"},
                ]
            )
    except ClientError as e:
        print(f"WARN: Could not discover disk metrics for {instance_id}. Error: {e}")
    metrics.append(
        [
            "AWS/EC2",
            "StatusCheckFailed",
            "InstanceId",
            instance_id,
            {"stat": "Maximum", "label": "Status Check"},
        ]
    )
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": metrics,
            "view": "timeSeries",
            "region": region,
            "title": title,
        },
    }


def create_linux_agent_widget(instance_id, region, y):
    title = f"EC2 Detailed (Agent): {instance_id} (Linux)"
    metrics = [
        [
            "CWAgent",
            "usage_active",
            "InstanceId",
            instance_id,
            "CustomDimensionName",
            "CPUMetric",
            {"label": "CPU Usage %"},
        ],
        [
            "...",
            "used_percent",
            "InstanceId",
            instance_id,
            "CustomDimensionName",
            "MEMMetric",
            {"label": "Memory Usage %"},
        ],
        [
            "...",
            "used_percent",
            "InstanceId",
            instance_id,
            "CustomDimensionName",
            "DISKMetric",
            "path",
            "/",
            {"label": "Disk Used % (/)"},
        ],
        [
            "AWS/EC2",
            "StatusCheckFailed",
            "InstanceId",
            instance_id,
            {"stat": "Maximum", "label": "Status Check"},
        ],
    ]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": metrics,
            "view": "timeSeries",
            "region": region,
            "title": title,
        },
    }


def create_standard_ec2_widget(instance_id, region, y, platform_name):
    title = f"EC2 Standard: {instance_id} ({platform_name})"
    metrics = [
        ["AWS/EC2", "CPUUtilization", "InstanceId", instance_id],
        ["...", "StatusCheckFailed", "InstanceId", instance_id, {"stat": "Maximum"}],
    ]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": metrics,
            "view": "timeSeries",
            "region": region,
            "title": title,
        },
    }


def create_rds_detailed_widget(arn, region, y):
    db = arn.split(":")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/RDS",
                    "CPUUtilization",
                    "DBInstanceIdentifier",
                    db,
                    {"label": "CPU"},
                ],
                ["...", "DatabaseConnections", {"label": "Connections"}],
                ["...", "FreeableMemory", {"label": "Freeable Memory"}],
                ["...", "FreeStorageSpace", {"label": "Free Storage"}],
                ["...", "DiskQueueDepth", {"label": "Disk Queue"}],
                ["...", "ReadLatency", {"label": "Read Latency"}],
                ["...", "WriteLatency", {"label": "Write Latency"}],
                ["...", "ReplicaLag", {"label": "Replica Lag"}],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"RDS Detailed: {db}",
        },
    }


def create_lambda_widget(arn, region, y):
    fn = arn.split(":")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                ["AWS/Lambda", "Errors", "FunctionName", fn, {"stat": "Sum"}],
                ["...", "Throttles", {"stat": "Sum"}],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"Lambda: {fn}",
        },
    }


def create_alb_widget(arn, region, y):
    lb = "/".join(arn.split("/")[-3:])
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/ApplicationELB",
                    "HTTPCode_Target_5XX_Count",
                    "LoadBalancer",
                    lb,
                    {"stat": "Sum"},
                ],
                ["...", "TargetConnectionErrorCount", {"stat": "Sum"}],
                [
                    "...",
                    "TargetResponseTime",
                    {"label": "Target Response Time (s)", "stat": "Average"},
                ],
                ["...", "UnHealthyHostCount", {"label": "Unhealthy Hosts"}],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"ALB: {lb.split('/')[1]}",
        },
    }


def create_nlb_widget(arn, region, y):
    lb = "/".join(arn.split("/")[-3:])
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/NetworkELB",
                    "TCP_Target_Reset_Count",
                    "LoadBalancer",
                    lb,
                    {"stat": "Sum"},
                ],
                ["...", "UnHealthyHostCount", {"label": "Unhealthy Hosts"}],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"NLB: {lb.split('/')[1]}",
        },
    }


def create_classic_elb_widget(arn, region, y):
    lb = arn.split(":")[-1].split("/")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/ELB",
                    "HTTPCode_ELB_5XX_Count",
                    "LoadBalancerName",
                    lb,
                    {"stat": "Sum"},
                ],
                ["...", "UnHealthyHostCount"],
                ["...", "Latency", {"stat": "Average"}],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"Classic ELB: {lb}",
        },
    }


def create_dynamodb_widget(arn, region, y):
    tbl = arn.split("/")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/DynamoDB",
                    "ThrottledRequests",
                    "TableName",
                    tbl,
                    {"stat": "Sum"},
                ],
                [
                    "...",
                    "SuccessfulRequestLatency",
                    "TableName",
                    tbl,
                    "Operation",
                    "GetItem",
                    {"label": "Get Latency (ms)"},
                ],
                [
                    "...",
                    "SuccessfulRequestLatency",
                    "TableName",
                    tbl,
                    "Operation",
                    "PutItem",
                    {"label": "Put Latency (ms)"},
                ],
                [
                    "...",
                    "SuccessfulRequestLatency",
                    "TableName",
                    tbl,
                    "Operation",
                    "DeleteItem",
                    {"label": "Delete Latency (ms)"},
                ],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"DynamoDB Performance: {tbl}",
        },
    }


def create_sqs_widget(arn, region, y):
    q = arn.split(":")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                ["AWS/SQS", "ApproximateAgeOfOldestMessage", "QueueName", q],
                ["...", "ApproximateNumberOfMessagesVisible"],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"SQS Queue: {q}",
        },
    }


def create_redshift_widget(arn, region, y):
    c = arn.split(":")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                ["AWS/Redshift", "CPUUtilization", "ClusterIdentifier", c],
                ["...", "HealthStatus", {"stat": "Minimum"}],
                ["...", "PercentageDiskSpaceUsed"],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"Redshift: {c}",
        },
    }


def create_sns_widget(arn, region, y):
    t = arn.split(":")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/SNS",
                    "NumberOfNotificationsFailed",
                    "TopicName",
                    t,
                    {"stat": "Sum"},
                ]
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"SNS Topic Failures: {t}",
        },
    }


def create_fsx_widget(arn, region, y):
    fs = arn.split("/")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/FSx",
                    "FreeStorageCapacity",
                    "FileSystemId",
                    fs,
                    {"stat": "Minimum"},
                ]
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"FSx Free Storage: {fs}",
        },
    }


def create_dx_widget(arn, region, y):
    c = arn.split("/")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                ["AWS/DX", "ConnectionState", "ConnectionId", c, {"stat": "Minimum"}]
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"Direct Connect State: {c}",
        },
    }


def create_vpn_widget(arn, region, y):
    vpn_id = arn.split("/")[-1]
    expression = f"SEARCH('{{AWS/VPN,TunnelIpAddress}} MetricName=\"TunnelState\" VpnId=\"{vpn_id}\"', 'Minimum', 300)"
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [{"expression": expression, "label": f"{vpn_id} Tunnel State"}]
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"VPN Connection: {vpn_id}",
        },
    }


def create_storagegateway_widget(arn, region, y):
    gw_id = arn.split("/")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/StorageGateway",
                    "CachePercentDirty",
                    "GatewayId",
                    gw_id,
                    {"stat": "Maximum"},
                ]
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"Storage Gateway: {gw_id}",
        },
    }


def create_elasticache_widget(arn, region, y):
    c = arn.split(":")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                ["AWS/ElastiCache", "CPUUtilization", "CacheClusterId", c],
                ["...", "DatabaseMemoryUsagePercentage"],
                ["...", "CacheMisses", {"stat": "Sum"}],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"ElastiCache: {c}",
        },
    }


def create_cloudfront_widget(arn, r, y):
    dist_id = arn.split("/")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/CloudFront",
                    "5xxErrorRate",
                    "Region",
                    "Global",
                    "DistributionId",
                    dist_id,
                ]
            ],
            "view": "timeSeries",
            "region": r,
            "title": f"CloudFront 5xx: {dist_id}",
        },
    }


def create_route53_widget(arn, r, y):
    healthcheck_id = arn.split("/")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/Route53",
                    "HealthCheckStatus",
                    "HealthCheckId",
                    healthcheck_id,
                    {"stat": "Minimum"},
                ]
            ],
            "view": "timeSeries",
            "region": r,
            "title": f"Route53 Health Check: {healthcheck_id}",
        },
    }


def create_acm_widget(arn, r, y):
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/CertificateManager",
                    "DaysToExpiry",
                    "CertificateArn",
                    arn,
                    {"stat": "Minimum"},
                ]
            ],
            "view": "singleValue",
            "region": r,
            "title": f"ACM Cert Expiry: ...{arn[-12:]}",
        },
    }


def create_ecs_widget(arn, r, y):
    p = arn.split("/")
    c, s = p[-2], p[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                ["AWS/ECS", "CPUUtilization", "ClusterName", c, "ServiceName", s],
                ["...", "MemoryUtilization"],
            ],
            "view": "timeSeries",
            "region": r,
            "title": f"ECS: {c}/{s}",
        },
    }
