# Automated CloudWatch Dashboard

This project provides a serverless solution to automatically create and manage a comprehensive and dynamic AWS CloudWatch Dashboard. It discovers resources based on predefined **tags** and generates a hybrid dashboard with high-level **Service Level Objectives (SLOs)**, detailed service-specific metrics, and advanced features like auto-discovered custom dimensions.

## ✨ Highlights and Key Features

* **Fully Dynamic and Automated**: The dashboard is generated based on environment variables, allowing for different configurations per environment (e.g., sandbox, production) without code changes.
* **Conditional SLO Monitoring**: Generates high-level SLO/SLI dashboards for key services **only if the required metrics are available**. This prevents broken or empty widgets and keeps the dashboard clean. Supported SLOs include:
  * **ALB, Lambda, and CloudFront** (Availability & Success Rate)
  * **EC2 and RDS** (Performance-Based SLOs for CPU & Latency)
* **Advanced EC2 Monitoring**: Intelligently detects if the CloudWatch Agent is installed on an EC2 instance. If detected, it **auto-discovers and displays all custom metrics** (e.g., memory, all disks), providing a complete view of your instance health.
* **Extensible and Customizable**:
  * **Custom Namespaces**: Add widgets for your own application-specific metrics that are not tied to a tagged resource.
  * **Custom Dimensions**: Specify the exact dimensions you want to monitor for any service.
* **Infrastructure as Code (IaC)**: The entire infrastructure is defined using AWS CloudFormation, ensuring repeatable and consistent deployments.
* **Wide Range of Supported Services**: Out-of-the-box support for over 20 AWS services, which can be enabled or disabled as needed.

---

## 🏗️ Architecture

The solution is entirely serverless and event-driven. The operation follows this flow:

1. **Scheduled Trigger**: An Amazon EventBridge rule triggers the Lambda function on a configurable schedule.
2. **Dynamic Lambda Execution**: The core Lambda function reads its configuration from environment variables and:
    * Uses the **Resource Groups Tagging API** to find all resources matching the specified **tags**.
    * **Intelligently builds SLO widgets** only if the underlying metric data exists.
    * Builds a list of detailed resource widgets based on the discovered services.
    * Adds any user-defined custom widgets from the `CustomWidgetsConfig` parameter.
    * Calls the `cloudwatch:PutDashboard` API to create or update the dashboard.
3. **CloudWatch Dashboard**: The final, updated dashboard is available in the CloudWatch console for monitoring.

---

## 🚀 Deployment and Customization

Deployment is managed via AWS CloudFormation. You can customize your dashboard by setting the following parameters in your `deployer.yaml` or a `config.json` file for your CI/CD pipeline.

### Core Parameters

* **`EnabledWidgets`**
  * **What it does:** A comma-separated list of service keys (e.g., `alb,ec2_instance,rds_instance`) to include on the dashboard.
  * **Why it's useful:** This gives you full control over the dashboard's content. The default list is curated for a focused view of core infrastructure and performance, but you can easily enable widgets for other services (like `acm_certificate` or `stepfunctions_statemachine`) for more specialized dashboards without changing the code.

* **`CustomWidgetsConfig`**
  * **What it does:** A JSON string representing an array of CloudWatch widget definitions for your custom namespaces.
  * **Why it's useful:** This is the best way to monitor metrics that are **not** tied to a specific, tagged AWS resource. Use this for your own application-level or business-level metrics. While the EC2 auto-discovery is powerful for resource-centric metrics, this parameter is essential for getting a complete picture of your application's health.
  * **Example**:

        ```json
        "[{\"type\":\"metric\",\"properties\":{\"metrics\":[[\"MyApplication\",\"UserSignUps\"]],\"title\":\"User Sign-Ups\"}}]"
        ```

* **`DimensionConfig`**
  * **What it does:** A JSON string to specify exact metric dimensions for AWS services, overriding the default discovery.
  * **Why it's useful:** This gives you fine-grained control for services where you might want to monitor a specific resource that isn't covered by the default logic. For example, you can use this to target a specific API Gateway method or a particular SQS queue.
  * **Example**:

        ```json
        "{\"AWS/ApiGateway\": [{\"Name\": \"ApiName\", \"Value\": \"MyProductionApi\"}]}"
        ```

* **SLO Target Parameters**
  * **What they do:** A full suite of parameters (`SLOTargetPercentage`, `CPUSLOTarget`, `RDSCpuSLOTarget`, `LatencySLOTarget`) to configure the targets for your various SLO widgets.
  * **Why it's useful:** This allows you to set different performance and availability targets for each of your environments (e.g., more lenient targets for sandbox vs. stricter targets for production).

---

## 🔧 Extending the Dashboard

To add monitoring support for a new AWS service:

1. **Update Service Configuration**: Open `lambda/index.py` and add a new entry to the `ALL_SERVICES_CONFIG` dictionary if it doesn't already exist.
2. **Create a Widget Builder Function**: If you've added a new service, create a new function in the same file that returns a CloudWatch dashboard widget JSON structure.
3. **Enable the Widget**: Add the key for your new service to the `EnabledWidgets` parameter during your next deployment.
