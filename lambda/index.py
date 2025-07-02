import boto3
import json
import os
from botocore.exceptions import ClientError
from botocore.config import Config

retry_config = Config(retries={"max_attempts": 5, "mode": "standard"})

ec2_client = boto3.client("ec2", config=retry_config)
cloudwatch_client = boto3.client("cloudwatch", config=retry_config)

# Full Master Configuration for all possible tag-based services
ALL_SERVICES_CONFIG = {
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
        "id": "loadbalancer",
        "builder": "create_classic_elb_widget",
    },
    "ecs_service": {
        "filter": "ecs:service",
        "id": "service/",
        "builder": "create_ecs_widget",
    },
    "eks_cluster": {
        "filter": "eks:cluster",
        "id": "cluster/",
        "builder": "create_eks_widget",
    },
    "dynamodb_table": {
        "filter": "dynamodb:table",
        "id": "table/",
        "builder": "create_dynamodb_widget",
    },
    "redshift_cluster": {
        "filter": "redshift:cluster",
        "id": "cluster:",
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
        "id": "cluster:",
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
    "apigateway_stage": {
        "filter": "apigateway:stages",
        "id": "apis/",
        "builder": "create_apigateway_widget",
    },
    "stepfunctions_statemachine": {
        "filter": "states",
        "id": "stateMachine:",
        "builder": "create_stepfunctions_widget",
    },
    "mq_broker": {
        "filter": "mq:broker",
        "id": "broker:",
        "builder": "create_mq_widget",
    },
}


def create_custom_widget(widget_def, region, y):
    widget_def["y"] = y
    if "properties" in widget_def:
        widget_def["properties"]["region"] = region
    return widget_def


def lambda_handler(event, context):
    region = os.environ["AWS_REGION"]
    dashboard_name = os.environ["DASHBOARD_NAME"]
    tag_key = os.environ["TAG_KEY"]
    tag_value = os.environ["TAG_VALUE"]

    slo_target = float(os.environ.get("SLO_TARGET", 99.9))
    cpu_slo_target = float(os.environ.get("CPU_SLO_TARGET", 80.0))
    rds_cpu_slo_target = float(os.environ.get("RDS_CPU_SLO_TARGET", 80.0))
    latency_slo_target_ms = float(os.environ.get("LATENCY_SLO_TARGET", 10.0))
    latency_slo_target_s = latency_slo_target_ms / 1000.0

    enabled_widget_keys = os.environ.get("ENABLED_WIDGETS").split(",")
    SERVICE_CONFIG = {
        key: ALL_SERVICES_CONFIG[key]
        for key in enabled_widget_keys
        if key in ALL_SERVICES_CONFIG
    }

    dimension_config_str = os.environ.get("DIMENSION_CONFIG", "{}")
    try:
        DIMENSION_CONFIG = json.loads(dimension_config_str)
    except json.JSONDecodeError:
        DIMENSION_CONFIG = {}

    tagged_resources = get_tagged_resources(tag_key, tag_value, SERVICE_CONFIG)

    if not tagged_resources:
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

    slo_resources = {
        "alb": [r for r in tagged_resources if "loadbalancer/app" in r["ResourceARN"]],
        "lambda": [r for r in tagged_resources if ":function:" in r["ResourceARN"]],
        "cloudfront": [
            r for r in tagged_resources if "distribution/" in r["ResourceARN"]
        ],
        "ec2": [r for r in tagged_resources if "instance/" in r["ResourceARN"]],
        "rds": [r for r in tagged_resources if ":db:" in r["ResourceARN"]],
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
    if slo_resources["ec2"] and metrics_exist_for_resources(
        "AWS/EC2", "CPUUtilization", "InstanceId", slo_resources["ec2"]
    ):
        all_widgets.extend(
            create_aggregate_ec2_slo_widget(
                slo_resources["ec2"], region, y_pos, cpu_slo_target
            )
        )
        y_pos += 6
    if slo_resources["rds"] and metrics_exist_for_resources(
        "AWS/RDS", "ReadLatency", "DBInstanceIdentifier", slo_resources["rds"]
    ):
        all_widgets.extend(
            create_aggregate_rds_slo_widget(
                slo_resources["rds"],
                region,
                y_pos,
                latency_slo_target_s,
                rds_cpu_slo_target,
                latency_slo_target_ms,
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

    sorted_resources = sorted(tagged_resources, key=lambda r: r["ResourceARN"])
    for resource in sorted_resources:
        arn = resource["ResourceARN"]
        matched_configs = [c for c in SERVICE_CONFIG.values() if c["id"] in arn]
        if not matched_configs:
            continue
        best_match_config = max(matched_configs, key=lambda c: len(c["id"]))
        try:
            if (
                best_match_config["builder"] == "create_classic_elb_widget"
                and "loadbalancer/" in arn
            ):
                continue
            is_global = best_match_config.get("is_global", False)
            widget_func = globals()[best_match_config["builder"]]
            widget = widget_func(
                arn, region if not is_global else "us-east-1", y_pos, DIMENSION_CONFIG
            )
            if widget:
                all_widgets.append(widget)
                y_pos += widget.get("height", 7)
        except Exception as e:
            print(
                f"ERROR: Could not create widget for ARN {arn}. Builder: {best_match_config['builder']}. Details: {e}"
            )

    custom_widgets_json = os.environ.get("CUSTOM_WIDGETS_CONFIG", "[]")
    try:
        custom_widget_defs = json.loads(custom_widgets_json)
        for widget_def in custom_widget_defs:
            custom_widget = create_custom_widget(widget_def, region, y_pos)
            if custom_widget:
                all_widgets.append(custom_widget)
                y_pos += widget_def.get("height", 7)
    except json.JSONDecodeError:
        print(
            f"WARN: Could not parse CUSTOM_WIDGETS_CONFIG. Invalid JSON: {custom_widgets_json}"
        )

    update_dashboard(dashboard_name, all_widgets)
    return {
        "statusCode": 200,
        "body": f"Dashboard updated successfully with {len(all_widgets)} widgets.",
    }


def get_tagged_resources(tag_key, tag_value, service_config):
    tagging_client = boto3.client("resourcegroupstaggingapi", config=retry_config)
    resources, token = [], ""
    filters = list(set([svc["filter"] for svc in service_config.values()]))
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
            return []
    return resources


def update_dashboard(dashboard_name, widgets):
    try:
        cloudwatch_client.put_dashboard(
            DashboardName=dashboard_name, DashboardBody=json.dumps({"widgets": widgets})
        )
    except ClientError as e:
        print(f"FATAL: Could not update dashboard '{dashboard_name}': {e}")


def metrics_exist_for_resources(namespace, metric_name, dimension_key, resources):
    try:
        paginator = cloudwatch_client.get_paginator("list_metrics")
        for resource in resources:
            instance_id = resource["ResourceARN"].split(":")[-1].split("/")[-1]
            pages = paginator.paginate(
                Namespace=namespace,
                MetricName=metric_name,
                Dimensions=[{"Name": dimension_key, "Value": instance_id}],
            )
            for page in pages:
                if page["Metrics"]:
                    print(f"INFO: Found metric '{metric_name}' for SLO widget.")
                    return True
    except ClientError as e:
        print(f"WARN: Error checking for metric '{metric_name}'. {e}")
        return False
    print(f"INFO: No metrics found for '{metric_name}' in the given resources.")
    return False


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
            "expression": f"100*(1-({total_errors_expression})/({total_requests_expression}+0.000001))",
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
            "title": "ALB Availability SLO",
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
            "expression": "100*(invocations-errors)/(invocations+0.000001)",
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
            "title": "Lambda Success Rate SLO",
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
            "region": "us-east-1",
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
            "region": "us-east-1",
            "title": "Current Success Rate",
        },
    }
    return [slo_graph, slo_value]


def create_aggregate_ec2_slo_widget(resources, region, y, slo_target):
    search_expression = " OR ".join(
        [f'"{res["ResourceARN"].split("/")[-1]}"' for res in resources]
    )
    metrics = [
        {
            "id": "avg_cpu",
            "expression": f"SEARCH('{{AWS/EC2,InstanceId}} MetricName=\"CPUUtilization\" ({search_expression})', 'Average', 300)",
            "visible": False,
        },
        {
            "id": "avg_mem",
            "expression": f"FILL(SEARCH('{{CWAgent,InstanceId}} MetricName=\"mem_used_percent\" ({search_expression})', 'Average', 300), 0)",
            "visible": False,
        },
        {
            "id": "slo",
            "expression": f"IF(avg_cpu < {slo_target} AND avg_mem < {slo_target}, 100, 0)",
            "label": "Performance SLO Met %",
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
            "title": f"EC2 Perf. SLO (CPU & Mem < {slo_target}%)",
            "yAxis": {"left": {"min": 0, "max": 105}},
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
            "title": "Current Performance",
        },
    }
    return [slo_graph, slo_value]


def create_aggregate_rds_slo_widget(
    resources, region, y, latency_target_s, cpu_target, latency_target_ms
):
    search_expression = " OR ".join(
        [f'"{res["ResourceARN"].split(":")[-1]}"' for res in resources]
    )
    metrics = [
        {
            "id": "avg_latency",
            "expression": f"(SEARCH('{{AWS/RDS,DBInstanceIdentifier}} MetricName=\"ReadLatency\" ({search_expression})', 'Average', 300) + SEARCH('{{AWS/RDS,DBInstanceIdentifier}} MetricName=\"WriteLatency\" ({search_expression})', 'Average', 300)) / 2",
            "visible": False,
        },
        {
            "id": "avg_cpu",
            "expression": f"SEARCH('{{AWS/RDS,DBInstanceIdentifier}} MetricName=\"CPUUtilization\" ({search_expression})', 'Average', 300)",
            "visible": False,
        },
        {
            "id": "slo",
            "expression": f"IF(avg_latency < {latency_target_s} AND avg_cpu < {cpu_target}, 100, 0)",
            "label": "Performance SLO Met %",
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
            "title": f"RDS Perf. SLO (Latency < {latency_target_ms}ms & CPU < {cpu_target}%)",
            "yAxis": {"left": {"min": 0, "max": 105}},
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
            "title": "Current Performance",
        },
    }
    return [slo_graph, slo_value]


def create_ec2_hybrid_widget(arn, region, y, dimension_config):
    instance_id = arn.split("/")[-1]
    try:
        agent_widget = create_dynamic_agent_widget(instance_id, region, y)
        if agent_widget:
            print(
                f"INFO: CWAgent metrics found for instance {instance_id}. Building dynamic agent widget."
            )
            return agent_widget
    except Exception as e:
        print(
            f"INFO: Could not build dynamic agent widget for {instance_id}. Defaulting to standard. Error: {e}"
        )
    print(
        f"INFO: CWAgent not detected for {instance_id}. Building standard agentless widget."
    )
    return create_standard_ec2_widget(instance_id, region, y)


def create_dynamic_agent_widget(instance_id, region, y):
    metrics_to_add = []
    try:
        paginator = cloudwatch_client.get_paginator("list_metrics")
        pages = paginator.paginate(
            Namespace="CWAgent",
            Dimensions=[{"Name": "InstanceId", "Value": instance_id}],
        )
        for page in pages:
            for metric in page["Metrics"]:
                metric_entry = ["CWAgent", metric["MetricName"]]
                for dim in metric["Dimensions"]:
                    metric_entry.append(dim["Name"])
                    metric_entry.append(dim["Value"])
                metrics_to_add.append(metric_entry)
        if not metrics_to_add:
            return None
    except ClientError as e:
        print(f"ERROR: Could not list CWAgent metrics for {instance_id}. {e}")
        return None
    metrics_to_add.append(
        ["AWS/EC2", "StatusCheckFailed", "InstanceId", instance_id, {"stat": "Maximum"}]
    )
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": metrics_to_add,
            "view": "timeSeries",
            "region": region,
            "title": f"EC2 Detailed (Auto-Discovered): {instance_id}",
        },
    }


def create_standard_ec2_widget(instance_id, region, y):
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                ["AWS/EC2", "CPUUtilization", "InstanceId", instance_id],
                [
                    "...",
                    "StatusCheckFailed",
                    "InstanceId",
                    instance_id,
                    {"stat": "Maximum"},
                ],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"EC2 Standard: {instance_id}",
        },
    }


def create_rds_detailed_widget(arn, region, y, dimension_config):
    db = arn.split(":")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", db],
                ["...", "DatabaseConnections"],
                ["...", "FreeableMemory"],
                ["...", "ReadLatency"],
                ["...", "WriteLatency"],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"RDS Detailed: {db}",
        },
    }


def create_lambda_widget(arn, region, y, dimension_config):
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


def create_alb_widget(arn, region, y, dimension_config):
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
                ["...", "TargetResponseTime", {"stat": "Average"}],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"ALB: {lb.split('/')[1]}",
        },
    }


def create_nlb_widget(arn, region, y, dimension_config):
    lb = "/".join(arn.split("/")[-3:])
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                ["AWS/NetworkELB", "UnHealthyHostCount", "LoadBalancer", lb],
                ["...", "TCP_Target_Reset_Count", {"stat": "Sum"}],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"NLB: {lb.split('/')[1]}",
        },
    }


def create_classic_elb_widget(arn, region, y, dimension_config):
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
                    "HTTPCode_Backend_5XX",
                    "LoadBalancerName",
                    lb,
                    {"stat": "Sum"},
                ],
                ["...", "UnHealthyHostCount"],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"Classic ELB: {lb}",
        },
    }


def create_ecs_widget(arn, r, y, dimension_config):
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


def create_eks_widget(arn, r, y, dimension_config):
    cluster_name = arn.split("/")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "ContainerInsights",
                    "node_cpu_utilization",
                    "ClusterName",
                    cluster_name,
                ],
                ["...", "node_memory_utilization"],
            ],
            "view": "timeSeries",
            "region": r,
            "title": f"EKS Cluster: {cluster_name}",
        },
    }


def create_dynamodb_widget(arn, region, y, dimension_config):
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
                ["...", "SuccessfulRequestLatency", "TableName", tbl],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"DynamoDB: {tbl}",
        },
    }


def create_redshift_widget(arn, region, y, dimension_config):
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
                ["...", "PercentageDiskSpaceUsed"],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"Redshift: {c}",
        },
    }


def create_sqs_widget(arn, region, y, dimension_config):
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


def create_sns_widget(arn, region, y, dimension_config):
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
            "title": f"SNS Topic: {t}",
        },
    }


def create_cloudfront_widget(arn, r, y, dimension_config):
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


def create_route53_widget(arn, r, y, dimension_config):
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


def create_acm_widget(arn, r, y, dimension_config):
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


def create_elasticache_widget(arn, region, y, dimension_config):
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
                ["...", "FreeableMemory"],
                ["...", "NetworkBytesIn"],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"ElastiCache: {c}",
        },
    }


def create_fsx_widget(arn, region, y, dimension_config):
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


def create_storagegateway_widget(arn, region, y, dimension_config):
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


def create_dx_widget(arn, region, y, dimension_config):
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
            "title": f"Direct Connect: {c}",
        },
    }


def create_vpn_widget(arn, region, y, dimension_config):
    vpn_id = arn.split("/")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    {
                        "expression": f"SEARCH('{{AWS/VPN,VpnId}} MetricName=\"TunnelState\" VpnId=\"{vpn_id}\"', 'Minimum', 300)"
                    }
                ]
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"VPN Tunnels: {vpn_id}",
        },
    }


def create_apigateway_widget(arn, region, y, dimension_config):
    parts = arn.split(":")
    api_info = parts[5].split("/")
    api_id = api_info[2]
    stage_name = api_info[4]
    api_gateway_dims = dimension_config.get(
        "AWS/ApiGateway", [{"Name": "ApiName", "Value": f"{api_id}/{stage_name}"}]
    )
    metrics = []
    for dim_set in api_gateway_dims:
        metrics.extend(
            [
                [
                    "AWS/ApiGateway",
                    "5XXError",
                    dim_set["Name"],
                    dim_set["Value"],
                    {"stat": "Sum"},
                ],
                ["...", "4XXError", {"stat": "Sum"}],
                ["...", "Latency", {"stat": "Average"}],
                ["...", "Count", {"stat": "Sum"}],
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
            "title": "API Gateway Performance",
        },
    }


def create_stepfunctions_widget(arn, region, y, dimension_config):
    sm_name = arn.split(":")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                [
                    "AWS/States",
                    "ExecutionsFailed",
                    "StateMachineArn",
                    arn,
                    {"stat": "Sum"},
                ],
                ["...", "ExecutionTime", {"stat": "Average"}],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"Step Functions: {sm_name}",
        },
    }


def create_mq_widget(arn, region, y, dimension_config):
    broker_name = arn.split(":")[-1]
    return {
        "type": "metric",
        "x": 0,
        "y": y,
        "width": 24,
        "height": 7,
        "properties": {
            "metrics": [
                ["AWS/AmazonMQ", "CpuUtilization", "Broker", broker_name],
                ["...", "TotalMessageCount"],
            ],
            "view": "timeSeries",
            "region": region,
            "title": f"Amazon MQ: {broker_name}",
        },
    }
