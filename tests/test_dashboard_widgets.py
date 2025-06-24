import boto3
import os
import json
import zipfile
import io
from moto import mock_aws

# Make sure to place this test file in a 'tests' folder where it can import
# the lambda function's code from the parent directory.
# e.g., from ..cloudwatch_automatic_dashboard.lambda import index
# For simplicity, assuming a direct import path here.
from cloudwatch_automatic_dashboard.lambda import index


# --- Test Setup Helper ---
def setup_test_environment():
    """Sets up mock AWS credentials and common Lambda environment variables."""
    os.environ["AWS_REGION"] = "us-east-1"
    os.environ["AWS_ACCESS_KEY_ID"] = "testing"
    os.environ["AWS_SECRET_ACCESS_KEY"] = "testing"
    os.environ["AWS_SECURITY_TOKEN"] = "testing"
    os.environ["AWS_SESSION_TOKEN"] = "testing"
    os.environ["SLO_TARGET"] = "99.9"

# --- Test Case for EC2 Instance ---
@mock_aws
def test_handler_with_tagged_ec2_instance():
    """
    Tests that the Lambda handler correctly creates a dashboard widget
    for a tagged EC2 instance.
    """
    # 1. Setup Mock Environment
    setup_test_environment()
    dashboard_name = "EC2-Test-Dashboard"
    tag_key = "ManagedBy"
    tag_value = "test-ec2"
    
    os.environ["DASHBOARD_NAME"] = dashboard_name
    os.environ["TAG_KEY"] = tag_key
    os.environ["TAG_VALUE"] = tag_value
    
    # Create mock boto3 clients
    ec2_client = boto3.client("ec2", region_name="us-east-1")
    cloudwatch_client = boto3.client("cloudwatch", region_name="us-east-1")
    tagging_client = boto3.client("resourcegroupstaggingapi", region_name="us-east-1")

    # 2. Create Mock EC2 Instance with Tags
    instance = ec2_client.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)
    instance_id = instance["Instances"][0]["InstanceId"]
    instance_arn = f"arn:aws:ec2:us-east-1:123456789012:instance/{instance_id}"
    
    tagging_client.tag_resources(
        ResourceARNList=[instance_arn],
        Tags={tag_key: tag_value}
    )

    # 3. Execute the Lambda Handler
    response = index.lambda_handler({}, {})

    # 4. Assert the Results
    assert response["statusCode"] == 200
    assert "Dashboard updated successfully" in response["body"]

    # 5. Verify the Dashboard Content
    dashboard = cloudwatch_client.get_dashboard(DashboardName=dashboard_name)
    dashboard_body = json.loads(dashboard["DashboardBody"])
    
    ec2_widget = next((w for w in dashboard_body.get("widgets", []) if "EC2 Standard" in w.get("properties", {}).get("title", "")), None)
            
    assert ec2_widget is not None, "EC2 widget was not found in the dashboard"
    assert ec2_widget["properties"]["title"] == f"EC2 Standard: {instance_id} (Linux)"
    
    metrics = ec2_widget["properties"]["metrics"]
    assert ["AWS/EC2", "CPUUtilization", "InstanceId", instance_id] in metrics
    assert ["...", "StatusCheckFailed", "InstanceId", instance_id, {"stat": "Maximum"}] in metrics

# --- Test Case for RDS Instance ---
@mock_aws
def test_handler_with_tagged_rds_instance():
    """
    Tests that the Lambda handler correctly creates a dashboard widget
    for a tagged RDS database instance.
    """
    # 1. Setup Mock Environment
    setup_test_environment()
    dashboard_name = "RDS-Test-Dashboard"
    tag_key = "ManagedBy"
    tag_value = "test-rds"
    db_instance_identifier = "test-db-instance"

    os.environ["DASHBOARD_NAME"] = dashboard_name
    os.environ["TAG_KEY"] = tag_key
    os.environ["TAG_VALUE"] = tag_value

    # Create mock clients
    rds_client = boto3.client("rds", region_name="us-east-1")
    cloudwatch_client = boto3.client("cloudwatch", region_name="us-east-1")
    tagging_client = boto3.client("resourcegroupstaggingapi", region_name="us-east-1")

    # 2. Create Mock RDS Instance with Tags
    db_instance = rds_client.create_db_instance(
        DBInstanceIdentifier=db_instance_identifier,
        DBInstanceClass="db.t3.micro",
        Engine="postgres",
    )
    db_instance_arn = db_instance["DBInstance"]["DBInstanceArn"]
    
    tagging_client.tag_resources(ResourceARNList=[db_instance_arn], Tags={tag_key: tag_value})

    # 3. Execute the Lambda Handler
    response = index.lambda_handler({}, {})

    # 4. Assert the Results
    assert response["statusCode"] == 200

    # 5. Verify the Dashboard Content
    dashboard = cloudwatch_client.get_dashboard(DashboardName=dashboard_name)
    dashboard_body = json.loads(dashboard["DashboardBody"])
    
    rds_widget = next((w for w in dashboard_body.get("widgets", []) if "RDS Detailed" in w.get("properties", {}).get("title", "")), None)
            
    assert rds_widget is not None, "RDS widget was not found in the dashboard"
    assert rds_widget["properties"]["title"] == f"RDS Detailed: {db_instance_identifier}"
    
    metrics = rds_widget["properties"]["metrics"]
    assert ["AWS/RDS", "CPUUtilization", "DBInstanceIdentifier", db_instance_identifier, {"label": "CPU"}] in metrics
    assert ["...", "DatabaseConnections", {"label": "Connections"}] in metrics

# --- Test Case for Application Load Balancer (ALB) ---
@mock_aws
def test_handler_with_tagged_alb():
    """
    Tests that the Lambda handler correctly creates a dashboard widget
    for a tagged Application Load Balancer.
    """
    # 1. Setup Mock Environment
    setup_test_environment()
    dashboard_name = "ALB-Test-Dashboard"
    tag_key = "ManagedBy"
    tag_value = "test-alb"
    lb_name = "test-alb"

    os.environ["DASHBOARD_NAME"] = dashboard_name
    os.environ["TAG_KEY"] = tag_key
    os.environ["TAG_VALUE"] = tag_value

    # Create mock clients
    elbv2_client = boto3.client("elbv2", region_name="us-east-1")
    ec2_client = boto3.client("ec2", region_name="us-east-1")
    cloudwatch_client = boto3.client("cloudwatch", region_name="us-east-1")
    tagging_client = boto3.client("resourcegroupstaggingapi", region_name="us-east-1")

    # 2. Create Mock ALB with Tags
    vpc = ec2_client.create_vpc(CidrBlock="10.0.0.0/16")
    subnet = ec2_client.create_subnet(VpcId=vpc["Vpc"]["VpcId"], CidrBlock="10.0.1.0/24")
    
    lb = elbv2_client.create_load_balancer(
        Name=lb_name,
        Subnets=[subnet["Subnet"]["SubnetId"]],
        Scheme="internal",
        Type="application",
        Tags=[{'Key': tag_key, 'Value': tag_value}]
    )
    lb_arn = lb["LoadBalancers"][0]["LoadBalancerArn"]
    
    tagging_client.tag_resources(ResourceARNList=[lb_arn], Tags={tag_key: tag_value})

    # 3. Execute the Lambda Handler
    response = index.lambda_handler({}, {})

    # 4. Assert the Results
    assert response["statusCode"] == 200

    # 5. Verify the Dashboard Content
    dashboard = cloudwatch_client.get_dashboard(DashboardName=dashboard_name)
    dashboard_body = json.loads(dashboard["DashboardBody"])
    
    alb_widget = next((w for w in dashboard_body.get("widgets", []) if "ALB:" in w.get("properties", {}).get("title", "")), None)

    assert alb_widget is not None, "ALB widget was not found"
    assert alb_widget["properties"]["title"] == f"ALB: {lb_name}"
    
    metrics = alb_widget["properties"]["metrics"]
    lb_arn_suffix = "/".join(lb_arn.split("/")[-3:])
    assert ["AWS/ApplicationELB", "HTTPCode_Target_5XX_Count", "LoadBalancer", lb_arn_suffix, {"stat": "Sum"}] in metrics

# --- Test Case for Lambda Function ---
@mock_aws
def test_handler_with_tagged_lambda_function():
    """
    Tests that the Lambda handler correctly creates a dashboard widget
    for a tagged Lambda function.
    """
    # 1. Setup Mock Environment
    setup_test_environment()
    dashboard_name = "Lambda-Test-Dashboard"
    tag_key = "ManagedBy"
    tag_value = "test-lambda"
    function_name = "my-test-function"

    os.environ["DASHBOARD_NAME"] = dashboard_name
    os.environ["TAG_KEY"] = tag_key
    os.environ["TAG_VALUE"] = tag_value

    # Create mock clients
    lambda_client = boto3.client("lambda", region_name="us-east-1")
    iam_client = boto3.client("iam", region_name="us-east-1")
    cloudwatch_client = boto3.client("cloudwatch", region_name="us-east-1")
    tagging_client = boto3.client("resourcegroupstaggingapi", region_name="us-east-1")

    # 2. Create Mock Lambda Function with Tags
    role = iam_client.create_role(
        RoleName="my-lambda-role",
        AssumeRolePolicyDocument=json.dumps({
            "Version": "2012-10-17",
            "Statement": [{"Effect": "Allow", "Principal": {"Service": "lambda.amazonaws.com"}, "Action": "sts:AssumeRole"}]
        })
    )
    
    zip_output = io.BytesIO()
    with zipfile.ZipFile(zip_output, 'w') as zf:
        zf.writestr('lambda_function.py', 'def handler(event, context): return "hello"')
    zip_output.seek(0)
    
    func = lambda_client.create_function(
        FunctionName=function_name,
        Runtime="python3.9",
        Role=role["Role"]["Arn"],
        Handler="lambda_function.handler",
        Code={"ZipFile": zip_output.read()},
        Tags={tag_key: tag_value}
    )
    func_arn = func["FunctionArn"]

    tagging_client.tag_resources(ResourceARNList=[func_arn], Tags={tag_key: tag_value})

    # 3. Execute the Lambda Handler
    response = index.lambda_handler({}, {})

    # 4. Assert the Results
    assert response["statusCode"] == 200

    # 5. Verify Dashboard Content
    dashboard = cloudwatch_client.get_dashboard(DashboardName=dashboard_name)
    dashboard_body = json.loads(dashboard["DashboardBody"])

    lambda_widget = next((w for w in dashboard_body.get("widgets", []) if "Lambda:" in w.get("properties", {}).get("title", "")), None)

    assert lambda_widget is not None, "Lambda widget was not found"
    assert lambda_widget["properties"]["title"] == f"Lambda: {function_name}"
    
    metrics = lambda_widget["properties"]["metrics"]
    assert ["AWS/Lambda", "Errors", "FunctionName", function_name, {"stat": "Sum"}] in metrics
