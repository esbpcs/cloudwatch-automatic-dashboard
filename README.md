# Automated CloudWatch Dashboard

This project provides a serverless solution to automatically create and manage a comprehensive and dynamic AWS CloudWatch Dashboard. It discovers resources based on predefined **tags** and generates a hybrid dashboard with high-level Service Level Objectives (SLOs), detailed service-specific metrics, and dynamic disk discovery for EC2 instances.

## Highlights and Key Features

* **Dynamic Resource Discovery**: Automatically discovers and visualizes a wide range of AWS services based on user-defined **tags**.
* **Aggregate SLO Monitoring**: Generates high-level SLO/SLI dashboards for key services to monitor availability and performance at a glance. Supported services include Application Load Balancer (ALB), AWS Lambda, and CloudFront.
* **Hybrid EC2 Monitoring**: Intelligently detects if the CloudWatch Agent is installed on an EC2 instance. If detected, it provides detailed widgets for memory and disk usage; otherwise, it defaults to standard EC2 metrics.
* **Infrastructure as Code (IaC)**: The entire infrastructure is defined using AWS CloudFormation, ensuring repeatable and consistent deployments.
* **Multi-Environment Configuration**: Easily manage deployments for different environments (e.g., development, staging, production) using a centralized `config.json` file.

## Architecture

The solution is entirely serverless and event-driven. The operation follows this flow:

1. **Scheduled Trigger**: An Amazon EventBridge (CloudWatch Events) rule triggers the Lambda function on a configurable schedule (e.g., once per day).
2. **Lambda Execution**: The core Lambda function executes, performing the following steps:
    * Reads configuration from its environment variables (e.g., dashboard name, **tags**).
    * Uses the **Resource Groups Tagging API** to find all resources matching the specified **tags**.
    * Builds a list of CloudWatch widgets in memory based on the discovered resources and their service type.
    * Calls the `cloudwatch:PutDashboard` API to create or update the dashboard with the generated widgets.
3. **CloudWatch Dashboard**: The final, updated dashboard is available in the CloudWatch console for monitoring.

## Supported Services & Tag Filtering

The script discovers resources by querying the **Resource Groups Tagging API** for specific resource types that have been tagged

| Service Category | AWS Service | Resource Type Filter |
| :--- | :--- | :--- |
| **Compute** | EC2 Instances | `ec2:instance` |
| | Lambda Functions | `lambda:function` |
| | ECS Services | `ecs:service` |
| **Databases** | RDS Instances | `rds:db` |
| | DynamoDB Tables | `dynamodb:table` |
| | ElastiCache Clusters | `elasticache:cluster` |
| | Redshift Clusters | `redshift:cluster` |
| **Networking & Content Delivery** | Application, Network, & Classic Load Balancers | `elasticloadbalancing:loadbalancer` |
| | VPN Connections | `ec2:vpn-connection` |
| | Direct Connect Connections | `directconnect:dxcon` |
| | CloudFront Distributions | `cloudfront:distribution` |
| | Route 53 Health Checks | `route53:healthcheck` |
| **Storage & Gateways** | FSx File Systems | `fsx:filesystem` |
| | Storage Gateways | `storagegateway:gateway` |
| **Application Integration** | SQS Queues | `sqs` |
| | SNS Topics | `sns` |
| **Security & Compliance** | ACM Certificates | `acm:certificate` |

## Deployment

1. **Package Application**: Zip the Lambda code from the `lambda/` directory.
2. **Upload Artifact**: Upload the code package to an S3 artifact bucket. You can create a secure, versioned bucket using the `artifact-bucket.yaml` template.
3. **Deploy Application**: Deploy the main CloudFormation stack using the `deployer.yaml` template, which creates the Lambda function and all related resources.

## Extending the Dashboard (Adding New Services)

To add monitoring support for a new AWS service, follow these steps:

1. **Update Service Configuration**: Open `lambda/index.py` and add a new entry to the `SERVICE_CONFIG` dictionary. You will need to define the `filter`, a unique `id` string from the ARN, and the widget `builder` function name.
2. **Create a Widget Builder Function**: In the same file, create a new function that returns a CloudWatch dashboard widget JSON structure for the new service.
3. **Add a Unit Test**: Create a new test case in the `tests/` directory to validate that your new widget builder function works correctly. The project is configured with `pytest` and `moto` for this purpose.

## Security, Quality, and Testing

This project includes a suite of development tools to ensure code quality, security, and correctness.

### Testing and Test Case Generation

The project is set up to use `pytest` for running tests and `moto` to mock AWS services, allowing you to test the Lambda function's logic without deploying it.

**It is strongly recommended to write test cases.** The absence of tests is a significant risk that can lead to bugs and broken deployments.

## Production and Cost Considerations

### Cost Estimation (ap-southeast-1 - Singapore)

**Disclaimer**: While this solution is designed to operate within the AWS Free Tier for typical usage, costs can increase. Be mindful of the Lambda schedule frequency and the number of monitored resources, as high volumes can lead to charges for API calls and log ingestion that exceed the free tier.

Based on the default configuration and typical usage, the estimated monthly cost for this solution is **$0.00**. The architecture is designed to operate almost entirely within the **AWS Free Tier**.
