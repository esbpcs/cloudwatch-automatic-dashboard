# Automated CloudWatch Dashboard

This project provides a serverless solution to automatically create and manage a comprehensive and dynamic AWS CloudWatch Dashboard. It discovers resources based on predefined tags and generates a hybrid dashboard with high-level Service Level Objectives (SLOs), detailed service-specific metrics, and dynamic disk discovery for EC2 instances.

## Highlights and Key Features

* **Dynamic Resource Discovery**: Automatically discovers and visualizes a wide range of AWS services based on user-defined tags. Services include EC2, RDS, Lambda, Load Balancers (ALB, NLB, Classic), ECS, DynamoDB, and many more.
* **Aggregate SLO Monitoring**: Generates high-level SLO/SLI dashboards for key services to monitor availability and performance at a glance. Supported services include Application Load Balancer (ALB), AWS Lambda, and CloudFront.
* **Hybrid EC2 Monitoring**: Intelligently detects if the CloudWatch Agent is installed on an EC2 instance. If detected, it provides detailed widgets for memory and disk usage; otherwise, it defaults to standard EC2 metrics.
* **Secure CI/CD Automation**: Includes CloudFormation templates to set up a secure, least-privilege CI/CD pipeline using GitHub Actions and OpenID Connect (OIDC) for passwordless deployments.
* **Multi-Environment Configuration**: Easily manage deployments for different environments (e.g., development, staging, production) using a centralized `config.json` file.
* **Infrastructure as Code (IaC)**: The entire infrastructure is defined using AWS CloudFormation, ensuring repeatable and consistent deployments.

## Architecture

The solution is entirely serverless and event-driven. The deployment and operation follow this flow:

1. **CI/CD Pipeline (GitHub Actions)**: A GitHub Actions workflow assumes an IAM Role via OIDC federation.
2. **Deployment Role**: The GitHub Actions role assumes a deployment role in the target AWS account, which has permissions to manage the project's resources.
3. **Artifact Storage**: The deployment pipeline places the zipped Lambda code into a secure S3 artifact bucket.
4. **Scheduled Trigger**: An Amazon EventBridge (CloudWatch Events) rule triggers the Lambda function on a configurable schedule (e.g., once per day).
5. **Lambda Execution**: The core Lambda function executes, performing the following steps:
    * Reads configuration from its environment variables (e.g., dashboard name, tags).
    * Uses the Resource Groups Tagging API to find all resources matching the `MonitoringTagKey` and `MonitoringTagValue`.
    * Builds a list of CloudWatch widgets in memory based on the discovered resources and their service type.
    * Calls the `cloudwatch:PutDashboard` API to create or update the dashboard with the generated widgets.
6. **CloudWatch Dashboard**: The final, updated dashboard is available in the CloudWatch console for monitoring.

## Deployment Workflow

The deployment process is separated into two distinct phases: a one-time setup of foundational resources and the automated deployment of the application, which is handled by a CI/CD workflow.

### 1. One-Time Manual Setup

These components are prerequisites and are typically deployed manually once per environment. They establish the foundation that your automated workflow will use.

* **S3 Artifact Bucket**: Stores the Lambda deployment package.
  * *File*: `cloudwatch-automatic-dashboard/artifact-bucket.yaml`
* **CI/CD Trust and Roles**: Establishes the secure OIDC trust relationship between GitHub Actions and AWS.
  * **Tooling Role & OIDC Provider**: The central role for GitHub Actions to assume.
    * *File*: `cloudwatch-automatic-dashboard/OIDC/tooling.yaml`
  * **Deployment Role**: The role in the target account that the Tooling Role assumes to manage application resources.
    * *File*: `cloudwatch-automatic-dashboard/OIDC/client.yaml`

### 2. Automated Workflow Steps

After the one-time setup is complete, a CI/CD pipeline (e.g., GitHub Actions) will automate all subsequent deployments and updates to the application. The workflow will perform these steps on every run:

* **Package Application**: Zipping the Lambda code.
  * *File*: `cloudwatch-automatic-dashboard/lambda/index.py`
* **Upload Artifact**: Uploading the code package to the S3 artifact bucket.
* **Deploy Application**: Deploying the main CloudFormation stack, which updates the Lambda function and its related resources.
  * *File*: `cloudwatch-automatic-dashboard/deployer.yaml`

## Extending the Dashboard (Adding New Services)

To add monitoring support for a new AWS service, follow these steps:

1. **Update Service Configuration**: Open `cloudwatch-automatic-dashboard/lambda/index.py` and add a new entry to the `SERVICE_CONFIG` dictionary. You will need to define:
    * `filter`: The resource type filter used by the Resource Groups Tagging API (e.g., `ec2:vpc`).
    * `id`: A unique string within the resource ARN that identifies the service.
    * `builder`: The name of the new widget-creation function you will build.
2. **Create a Widget Builder Function**: In the same file, create a new function (e.g., `create_new_service_widget(arn, region, y)`) that returns a CloudWatch dashboard widget JSON structure for the new service.
3. **Update Resource Discovery**: In the `get_tagged_resources` function, ensure the `ResourceTypeFilters` list includes the new service's filter value you defined in `SERVICE_CONFIG`.
4. **Add a Unit Test**: Create a new test case in the `tests/` directory to validate that your new widget builder function works correctly. The project is already configured with `pytest` and `moto` for this purpose.

## Security, Quality, and Testing

This project includes a suite of development tools to ensure code quality, security, and correctness. These should be integrated as steps in your CI/CD workflow before deployment.

### Workflow Security Tools

The following tools are defined in `requirements-dev.txt` and provide automated security checks:

* **Static Application Security Testing (SAST)**: `bandit` scans the Python code for common security vulnerabilities.
  * *Command*: `bandit -r cloudwatch-automatic-dashboard/lambda/`
* **Dependency Vulnerability Scanning**: `safety` checks the project's Python dependencies against a database of known vulnerabilities.
  * *Command*: `safety check -r requirements-dev.txt`
* **CloudFormation Linting**: `cfn-lint` validates the CloudFormation templates against AWS best practices, including security configurations.
  * *Command*: `cfn-lint cloudwatch-automatic-dashboard/**/*.yaml`

### Testing and Test Case Generation

The project is set up to use `pytest` for running tests and `moto` to mock AWS services, allowing you to test the Lambda function's logic without deploying it.

**It is strongly recommended to write test cases.** The absence of tests is a significant risk that can lead to bugs and broken deployments.

## Production and Cost Considerations

### Cost Estimation (ap-southeast-1 - Singapore)

**Disclaimer**: While this solution is designed to operate within the AWS Free Tier for typical usage, costs can increase. Be mindful of the Lambda schedule frequency and the number of monitored resources, as high volumes can lead to charges for API calls and log ingestion that exceed the free tier.

Based on the default configuration and typical usage, the estimated monthly cost for this solution is **$0.00**. The architecture is designed to operate almost entirely within the **AWS Free Tier**.

Here is a detailed breakdown:

* **AWS Lambda**:
  * **Free Tier**: 1 million requests and 400,000 GB-seconds of compute time per month.
  * **Estimated Usage**: With a daily run, you will have ~30 requests and well under 1,000 GB-seconds of compute time, resulting in a **$0.00** charge.
* **Amazon S3**:
  * **Free Tier**: 5 GB of storage, 20,000 Get requests, and 2,000 Put requests per month.
  * **Estimated Usage**: Storing a few megabytes for the Lambda artifact is negligible, resulting in a **$0.00** charge.
* **Amazon CloudWatch**:
  * **Free Tier**: 3 dashboards, 1 million API requests, and 5 GB of log ingestion/storage per month.
  * **Estimated Usage**: The project creates 1 dashboard and makes a minimal number of API calls and logs, well within the free tier. This results in a **$0.00** charge.
* **Amazon EventBridge**:
  * **Free Tier**: 14 million scheduled invocations per month.
  * **Estimated Usage**: ~30 invocations per month for the daily schedule results in a **$0.00** charge.
